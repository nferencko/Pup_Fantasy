#!/usr/bin/env python3
"""
Pulls rest-of-season and weekly projections from several public sources,
re-scores them with YOUR league rules, blends them, and writes data/data.js
for the website.  Standard library only.  Run:  python update_data.py

Sources
  1. Rotowire projections (via Sleeper's public API): full stat lines, so we can
     score them ourselves, including rushing / receiving first downs.
  2. FantasyPros expert consensus rankings (ROS half-PPR + weekly half-PPR).
     These are ranks, not points, so they are converted to points by mapping
     each rank onto the Rotowire points curve, then averaged with Rotowire.

To add another source, add a function that returns {player_key: points} for
ROS and for the week, and append it to the lists in build().
"""
import json, re, sys, time, unicodedata, datetime, pathlib, html, os, pickle
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

# ----------------------------------------------------------------- league config
# Your stated rules: 0.5 PPR, +0.5 per rushing first down, +0.5 per receiving first down.
# Everything else is assumed standard - edit here if your league differs.
SCORING = {
    "rec": 0.5, "rush_fd": 0.5, "rec_fd": 0.5,
    "pass_yd": 0.04, "pass_td": 4, "pass_int": -2, "pass_2pt": 2,
    "rush_yd": 0.1, "rush_td": 6, "rush_2pt": 2,
    "rec_yd": 0.1, "rec_td": 6, "rec_2pt": 2,
    "fum_lost": -2,
}
# League: 10 teams, superflex. Assumed lineup: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX (RB/WR/TE),
# 1 SUPERFLEX (QB/RB/WR/TE). Edit LINEUP / TEAMS if yours differs.
TEAMS = 10
LINEUP = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SUPERFLEX": 1}
# Share of each flex slot that ends up filled by each position. Superflex slots go to a
# QB almost every time (a QB scores more than a comparable RB/WR), which is what makes QBs
# so valuable in this format.
FLEX_SPLIT = {"FLEX": {"RB": 0.45, "WR": 0.45, "TE": 0.10},
              "SUPERFLEX": {"QB": 0.85, "RB": 0.07, "WR": 0.07, "TE": 0.01}}
# Superflex trade markets price QBs above their pure points value (a QB can fill two starting
# slots and good ones are scarce). Applied ONLY to the trade calculator's "tradeValue";
# rankings stay based on projected points. 1.0 = no premium.
QB_TRADE_PREMIUM = 1.3
BENCH_BUFFER = 1.0  # replacement = first player AFTER the starters, plus this many extra


def replacement_ranks():
    out = {}
    for pos in ("QB", "RB", "WR", "TE"):
        starters = LINEUP.get(pos, 0) + sum(LINEUP[f] * sp.get(pos, 0) for f, sp in FLEX_SPLIT.items())
        out[pos] = round(starters * TEAMS + BENCH_BUFFER)
    return out


REPLACEMENT_RANK = replacement_ranks()  # {'QB': 20, 'RB': 25, 'WR': 25, 'TE': 12} for the lineup above
POSITIONS = ["QB", "RB", "WR", "TE"]
LAST_WEEK = 18  # last regular-season week
OUT = pathlib.Path(__file__).parent / "data" / "data.js"
UA = {"User-Agent": "Mozilla/5.0 (fantasy-ros-site personal project)"}
CACHE_DIR = pathlib.Path(__file__).parent / "data" / "cache"   # last good copy of each source
MAX_CACHE_DAYS = 10   # a saved copy older than this is not used
MIN_SOURCES = 3       # refuse to publish rankings built from fewer working sources


def get(url, tries=3):
    for i in range(tries):
        try:
            with urlopen(Request(url, headers=UA), timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def norm(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", s)
    return re.sub(r"[^a-z]", "", s)


# Every projected stat the site can score. The page re-scores these with the user's league settings,
# so the data file carries raw stat lines (not just points). Both stat-line sources provide all of them.
STAT_KEYS = ["pass_yd", "pass_td", "pass_int", "pass_2pt", "pass_cmp", "pass_inc", "pass_sack", "pass_fd",
             "rush_att", "rush_yd", "rush_td", "rush_2pt", "rush_fd",
             "rec", "rec_tgt", "rec_yd", "rec_td", "rec_2pt", "rec_fd", "fum_lost"]
DEEP_KEEP_RANK = 60   # rank-only players ranked better than this are kept in the data (the page decides who is "deep")


def score(stats):
    return sum(stats.get(k, 0) * v for k, v in SCORING.items())


# ------------------------------------------------------------------ Rotowire
def rotowire_week(season, wk):
    q = "&".join(f"position[]={p}" for p in POSITIONS)
    url = f"https://api.sleeper.com/projections/nfl/{season}/{wk}?season_type=regular&{q}&company=rotowire"
    return wk, json.loads(get(url))


def fetch_rotowire(season, cur_week):
    weeks = list(range(cur_week, LAST_WEEK + 1))
    with ThreadPoolExecutor(6) as ex:
        results = list(ex.map(lambda w: rotowire_week(season, w), weeks))
    players = {}
    for wk, rows in results:
        for r in rows:
            st, pl = r.get("stats") or {}, r["player"]
            pts = score(st)
            if pts <= 0 or not st.get("gp", 1):
                continue
            pos = pl.get("position")
            if pos not in POSITIONS:
                continue
            key = (norm(f"{pl['first_name']} {pl['last_name']}"), pos)
            p = players.setdefault(key, {
                "name": f"{pl['first_name']} {pl['last_name']}", "pos": pos,
                "team": pl.get("team") or r.get("team") or "FA",
                "inj": pl.get("injury_status"), "weeks": {}, "stats": {}, "opp": {}})
            p["weeks"][wk] = round(pts, 2)
            p["stats"][wk] = {k: round(st[k], 4) for k in STAT_KEYS if st.get(k)}
            p["opp"][wk] = r.get("opponent")
    return players


# ---------------------------------------------------------------------- ESPN
# ESPN's public projections come as stat lines too (including first downs, ids 212/213), so
# they are re-scored with the same league rules as Rotowire.
ESPN_STATS = {3: "pass_yd", 4: "pass_td", 19: "pass_2pt", 20: "pass_int",
              24: "rush_yd", 25: "rush_td", 26: "rush_2pt", 212: "rush_fd",
              42: "rec_yd", 43: "rec_td", 44: "rec_2pt", 53: "rec", 213: "rec_fd", 72: "fum_lost",
              1: "pass_cmp", 2: "pass_inc", 64: "pass_sack", 211: "pass_fd", 23: "rush_att", 58: "rec_tgt"}
ESPN_POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE"}
ESPN_TEAMS = {1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET",
              9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR", 15: "MIA", 16: "MIN",
              17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC",
              25: "SF", 26: "SEA", 27: "TB", 28: "WSH", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU"}


ESPN_IDS = {}  # (name, pos) -> ESPN player id, used for headshots on the site
ESPN_OWN = {}  # (name, pos) -> (% owned in ESPN leagues, recent change), used for the waiver wire


def fetch_espn(season, cur_week):
    flt = json.dumps({"players": {
        "filterStatus": {"value": ["FREEAGENT", "WAIVERS", "ONTEAM"]},
        "filterSlotIds": {"value": [0, 2, 4, 6]},          # QB, RB, WR, TE
        "limit": 1000, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}})
    url = (f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
           f"/segments/0/leaguedefaults/3?scoringPeriodId={cur_week}&view=kona_player_info")
    req = Request(url, headers={**UA, "x-fantasy-filter": flt})
    for i in range(3):
        try:
            with urlopen(req, timeout=90) as r:
                rows = json.loads(r.read().decode("utf-8", "replace"))["players"]
            break
        except Exception:
            if i == 2:
                raise
            time.sleep(2)
    players = {}
    for row in rows:
        pl = row["player"]
        pos = ESPN_POS.get(pl.get("defaultPositionId"))
        if not pos:
            continue
        ESPN_IDS[(norm(pl["fullName"]), pos)] = pl.get("id")
        own = pl.get("ownership") or {}
        if own.get("percentOwned") is not None:
            ESPN_OWN[(norm(pl["fullName"]), pos)] = (own["percentOwned"], own.get("percentChange") or 0)
        weeks, wstats = {}, {}
        for st in pl.get("stats", []):
            # projected (source 1), single-week (split 1) lines for this season, remaining weeks only
            if (st.get("seasonId") == int(season) and st.get("statSourceId") == 1
                    and st.get("statSplitTypeId") == 1 and cur_week <= st.get("scoringPeriodId", 0) <= LAST_WEEK):
                stats = {ESPN_STATS[int(k)]: v for k, v in st.get("stats", {}).items() if int(k) in ESPN_STATS}
                pts = score(stats)
                if pts > 0:
                    weeks[st["scoringPeriodId"]] = round(pts, 2)
                    wstats[st["scoringPeriodId"]] = {k: round(v, 4) for k, v in stats.items() if v}
        if weeks:
            players[(norm(pl["fullName"]), pos)] = {
                "name": pl["fullName"], "pos": pos, "team": ESPN_TEAMS.get(pl.get("proTeamId"), "FA"),
                "inj": None if pl.get("injuryStatus") in (None, "ACTIVE") else pl["injuryStatus"],
                "weeks": weeks, "stats": wstats, "opp": {}}
    return players


# --------------------------------------------------------------- FantasyPros
def fp_ecr(path):
    html = get(f"https://www.fantasypros.com/nfl/rankings/{path}.php")
    i = html.index("var ecrData = ") + len("var ecrData = ")
    data, _ = json.JSONDecoder().raw_decode(html[i:])
    return data


def fp_rows(data):
    out = {}
    for r in data["players"]:
        pos = re.sub(r"\d+", "", r.get("player_position_id", ""))
        if pos in POSITIONS:
            out[(norm(r["player_name"]), pos)] = {
                "rank": float(r["rank_ave"] or r["rank_ecr"]),
                "bye": r.get("player_bye_week"), "team": r.get("player_team_id"),
                "name": r["player_name"]}
    return out


# ---------------------------------------------------------------- Flock Fantasy
# Public JSON behind flockfantasy.com's rankings pages (no login needed). Each row carries the
# individual expert ranks, so we average the positional ranks ourselves for a fractional value.
# "redraft_sf" is Flock's superflex redraft board (in-season this is rest-of-season); positional
# order is used, so points stay format-independent like the FantasyPros per-position pages.
def flock_rows(fmt, season):
    url = f"https://api.flockfantasy.com/rankings?format={fmt}&pickType=general&year={season}"
    rows = json.loads(get(url)).get("data", [])
    out = {}
    for r in rows:
        pos = r.get("position")
        if pos not in POSITIONS or r.get("isDraftPick"):
            continue
        ranks = [v for v in (r.get("positionalRanks") or {}).values() if v is not None]
        rank = sum(ranks) / len(ranks) if ranks else r.get("averagePositionalRank")
        if rank is None:
            continue
        out[(norm(r["playerName"]), pos)] = {"rank": float(rank), "name": r["playerName"],
                                             "team": r.get("team"), "bye": r.get("byeWeek")}
    return out


# ---------------------------------------------------------------- Draft Sharks
# Draft Sharks' ranking tables are filled in by an HTMX call (/ros-rankings/load-table and
# /weekly-rankings/load-table) that returns HTML. Each player is a <tbody data-player-row> with the name,
# position and positional rank in attributes. One request per position gives much deeper lists than the
# overall board (which stops at 250 players, mostly WR/QB). Half-PPR board; positional rank is used.
def draftsharks_pos(kind, pos, week):
    base = "https://www.draftsharks.com"
    url = (f"{base}/ros-rankings/load-table?pprSuperflexSlug=half-ppr&fantasyPosition={pos}&researchDepth=rankings&playerGroup=all"
           if kind == "ros" else
           f"{base}/weekly-rankings/load-table?week={week}&pprSuperflexSlug=half-ppr&fantasyPosition={pos}&researchDepth=rankings&playerGroup=all")
    page, out, seen = get(url), {}, 0
    for m in re.finditer(r"<tbody\s+data-player-row(.*?)</tr>", page, re.S):
        seen += 1
        blk = m.group(1)
        name = re.search(r'data-player-name="([^"]*)"', blk)
        ppos = re.search(r'data-fantasy-position="([^"]*)"', blk)
        rank = re.search(r"<pos-roster-spot[^>]*>(\d+)<", blk)
        team = re.search(r'player-details-group__team-name">([^<]*)<', blk)
        if not (name and ppos and rank) or ppos.group(1) != pos:
            continue
        nm = html.unescape(name.group(1))
        out[(norm(nm), pos)] = {"rank": float(rank.group(1)), "name": nm, "team": team.group(1) if team else None}
    if not seen:
        raise ValueError("Draft Sharks page has no player rows: its layout or endpoint probably changed")
    if not out:
        raise ValueError(f"Draft Sharks: found {seen} rows but none readable for {pos}: its markup probably changed")
    return out


def draftsharks_rows(kind, week):
    with ThreadPoolExecutor(4) as ex:
        parts = list(ex.map(lambda pos: draftsharks_pos(kind, pos, week), POSITIONS))
    merged = {}
    for p in parts:
        merged.update(p)
    return merged


# ---------------------------------------------------------------- FantasyCalc
# Public trade-value API, set to this league's format (redraft, 10 teams, superflex, 0.5 PPR). It is a
# trade-market signal, not a projection; its positional order is used as one more ROS ranking. Covers only
# the ~200 most-traded players and has no weekly numbers.
def fantasycalc_rows():
    qbs = 2 if LINEUP.get("SUPERFLEX") else 1
    url = f"https://api.fantasycalc.com/values/current?isDynasty=false&numQbs={qbs}&numTeams={TEAMS}&ppr={SCORING['rec']}"
    out = {}
    for r in json.loads(get(url)):
        pl = r["player"]
        pos = pl.get("position")
        if pos not in POSITIONS:
            continue
        out[(norm(pl["name"]), pos)] = {"rank": float(r["positionRank"]), "name": pl["name"],
                                        "team": pl.get("maybeTeam"), "espnId": pl.get("espnId")}
    return out


def curve_points(rank, curve):
    """Map a (possibly fractional) 1-based rank onto a descending points curve."""
    if not curve:
        return 0
    x = max(rank - 1, 0)
    lo = int(x)
    if lo >= len(curve) - 1:
        return curve[-1]
    f = x - lo
    return curve[lo] * (1 - f) + curve[lo + 1] * f


# ------------------------------------------------------------ source safety net
# Every source is fetched through load_source(): the result is validated, saved as a "last good" copy,
# and if the live fetch fails or looks wrong (site down, layout changed, far too few players) the last
# good copy is used instead, for up to MAX_CACHE_DAYS. If there is no usable copy, that source is left
# out of the averages. The outcome is written to data.js as `sourceStatus` and shown on the site.
def need(label, n, minimum):
    return f"only {n} {label} found (expected at least {minimum})" if n < minimum else None


def first_problem(*checks):
    return next((c for c in checks if c), None)


def load_source(name, fetch, validate, empty, week, weekly_idx=()):
    """fetch() -> tuple of dicts. Returns (data tuple, status dict)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / (re.sub(r"[^a-z0-9]+", "_", name.lower()) + ".pkl")
    now = datetime.datetime.now()
    try:
        data = fetch()
        problem = validate(data)
        if problem:
            raise ValueError(problem)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            pickle.dump({"data": data, "week": week, "ts": now}, f)
        os.replace(tmp, path)
        return data, {"name": name, "status": "ok", "asOf": now.strftime("%Y-%m-%d"), "detail": ""}
    except Exception as e:
        why = (str(e) or type(e).__name__).replace("\n", " ")[:160]
        if path.exists():
            try:
                with open(path, "rb") as f:
                    c = pickle.load(f)
                if (now - c["ts"]).days <= MAX_CACHE_DAYS:
                    data = list(c["data"])
                    for i in weekly_idx:           # last week's weekly ranks would be wrong this week
                        if c["week"] != week:
                            data[i] = empty[i]
                    return tuple(data), {"name": name, "status": "cached", "asOf": c["ts"].strftime("%Y-%m-%d"), "detail": why}
            except Exception:
                pass                                # unreadable cache: treat as no cache
        return empty, {"name": name, "status": "missing", "asOf": None, "detail": why}


def espn_bundle(season, week):
    ESPN_IDS.clear()
    ESPN_OWN.clear()
    players = fetch_espn(season, week)
    return players, dict(ESPN_IDS), dict(ESPN_OWN)


# --------------------------------------------------------------------- build
def build():
    state = json.loads(get("https://api.sleeper.app/v1/state/nfl"))
    season, week = state["season"], state["week"]
    print(f"Season {season}, week {week}")

    statuses = []

    def src(name, fetch, validate, empty, weekly=()):
        data, st = load_source(name, fetch, validate, empty, week, weekly)
        statuses.append(st)
        note = {"ok": "ok", "cached": f"USING SAVED COPY from {st['asOf']} ({st['detail']})",
                "missing": f"UNAVAILABLE, left out ({st['detail']})"}[st["status"]]
        print(f"{name}: {note}")
        return data

    no_pos = lambda: {p: {} for p in POSITIONS}
    by_pos = lambda d_, p: sum(1 for k in d_ if k[1] == p)

    (roto,) = src("Rotowire", lambda: (fetch_rotowire(season, week),),
                  lambda d_: need("players", len(d_[0]), 150), ({},))
    espn, espn_ids, espn_own = src("ESPN", lambda: espn_bundle(season, week),
                                   lambda d_: first_problem(need("players", len(d_[0]), 150), need("ownership rows", len(d_[2]), 300)),
                                   ({}, {}, {}))
    ESPN_IDS.clear(); ESPN_IDS.update(espn_ids)
    ESPN_OWN.clear(); ESPN_OWN.update(espn_own)

    # Per-position ROS rankings keep points honest regardless of league format; superflex /
    # flex scarcity is handled afterwards by the replacement levels.
    def fetch_fp():
        ros = {pos: fp_rows(fp_ecr(path)) for pos, path in
               [("QB", "ros-qb"), ("RB", "ros-half-point-ppr-rb"),
                ("WR", "ros-half-point-ppr-wr"), ("TE", "ros-half-point-ppr-te")]}
        wk = {pos: fp_rows(fp_ecr(path)) for pos, path in
              [("QB", "qb"), ("RB", "half-point-ppr-rb"),
               ("WR", "half-point-ppr-wr"), ("TE", "half-point-ppr-te")]}
        return ros, wk
    fp_ros, fp_wk = src("FantasyPros", fetch_fp,
                        lambda d_: first_problem(*[need(f"{p} ROS ranks", len(d_[0][p]), 10) for p in POSITIONS],
                                                 *[need(f"{p} weekly ranks", len(d_[1][p]), 10) for p in POSITIONS]),
                        (no_pos(), no_pos()), weekly=(1,))

    MIN_DS = {"QB": 15, "RB": 40, "WR": 60, "TE": 25}
    ds_ros, ds_wk = src("Draft Sharks", lambda: (draftsharks_rows("ros", week), draftsharks_rows("weekly", week)),
                        lambda d_: first_problem(*[need(f"{p} ROS ranks", by_pos(d_[0], p), m) for p, m in MIN_DS.items()],
                                                 need("weekly ranks", len(d_[1]), 80)),
                        ({}, {}), weekly=(1,))
    (fcalc,) = src("FantasyCalc", lambda: (fantasycalc_rows(),), lambda d_: need("players", len(d_[0]), 80), ({},))
    flock_ros, flock_wk = src("Flock Fantasy", lambda: (flock_rows("redraft_sf", season), flock_rows("weekly", season)),
                              lambda d_: first_problem(need("ROS ranks", len(d_[0]), 100), need("weekly ranks", len(d_[1]), 50)),
                              ({}, {}), weekly=(1,))

    live = [s for s in statuses if s["status"] != "missing"]
    if (not roto and not espn) or len(live) < MIN_SOURCES:
        raise SystemExit("Not enough working sources to build rankings (need a Rotowire or ESPN projection plus "
                         f"{MIN_SOURCES - 1}+ others). Leaving the existing data file untouched.")
    print(f"Sources in use: {len(live)} of {len(statuses)}")

    # Rank -> points curves, per position, built from the stat-line sources (Rotowire + ESPN)
    def ros_sum(p):            # saved copies may still hold weeks that have already been played
        return sum(v for w, v in p["weeks"].items() if w >= week)
    roto_ros = {k: v for k, p in roto.items() if (v := ros_sum(p)) > 0}
    espn_ros = {k: v for k, p in espn.items() if (v := ros_sum(p)) > 0}
    stat_ros = {}
    for k in set(roto_ros) | set(espn_ros):
        v = [x for x in (roto_ros.get(k), espn_ros.get(k)) if x is not None]
        stat_ros[k] = sum(v) / len(v)
    ros_curve = {pos: sorted((v for k, v in stat_ros.items() if k[1] == pos), reverse=True)
                 for pos in POSITIONS}
    stat_wk = {}
    for k in set(roto) | set(espn):
        v = [src[k]["weeks"][week] for src in (roto, espn) if k in src and week in src[k]["weeks"]]
        if v:
            stat_wk[k] = sum(v) / len(v)
    wk_curve = {pos: sorted((v for k, v in stat_wk.items() if k[1] == pos), reverse=True)
                for pos in POSITIONS}

    def stat_sum(src):   # projected stat totals from this week on (the page scores them with the user's settings)
        tot = {}
        for w, st in ((src or {}).get("stats") or {}).items():
            if w >= week:
                for k, v in st.items():
                    tot[k] = round(tot.get(k, 0) + v, 4)
        return tot or None

    def stat_week(src):
        return (((src or {}).get("stats") or {}).get(week)) or None

    keys = set(roto) | set(espn) | {k for d in fp_ros.values() for k in d} | set(flock_ros) | set(fcalc) | set(ds_ros)
    players = []
    for key in keys:
        pos = key[1]
        r, e, f = roto.get(key), espn.get(key), fp_ros[pos].get(key)
        fl, fc, dsr = flock_ros.get(key), fcalc.get(key), ds_ros.get(key)
        ros_r, ros_e = roto_ros.get(key), espn_ros.get(key)
        ros_f = curve_points(f["rank"], ros_curve[pos]) if f else None
        ros_k = curve_points(fl["rank"], ros_curve[pos]) if fl else None
        ros_c = curve_points(fc["rank"], ros_curve[pos]) if fc else None
        ros_d = curve_points(dsr["rank"], ros_curve[pos]) if dsr else None
        # Rank-only players (no stat-line projection) are usually deep bench / injured: skip unless ranked well
        best_rank = min([x["rank"] for x in (f, fl, fc, dsr) if x] or [999])
        deep = ros_r is None and ros_e is None and best_rank > REPLACEMENT_RANK[pos] + 10
        if deep and best_rank > DEEP_KEEP_RANK:
            continue
        parts = [x for x in (ros_r, ros_e, ros_f, ros_k, ros_c, ros_d) if x is not None]
        ros = sum(parts) / len(parts)

        wk_r = r["weeks"].get(week) if r else None
        wk_e = e["weeks"].get(week) if e else None
        fw = fp_wk[pos].get(key)
        wk_f = curve_points(fw["rank"], wk_curve[pos]) if fw else None
        fk = flock_wk.get(key)
        wk_k = curve_points(fk["rank"], wk_curve[pos]) if fk else None
        dsw = ds_wk.get(key)
        wk_d = curve_points(dsw["rank"], wk_curve[pos]) if dsw else None
        wparts = [x for x in (wk_r, wk_e, wk_f, wk_k, wk_d) if x is not None]
        base = r or e or fl or fc or dsr or {}
        players.append({
            "id": f"{key[0]}-{pos}",
            "name": base.get("name") or (f or fl or fc or dsr)["name"],
            "pos": pos,
            "team": base.get("team") or (f or {}).get("team") or (fl or {}).get("team") or (fc or {}).get("team") or (dsr or {}).get("team") or "FA",
            "inj": (r or {}).get("inj") or (e or {}).get("inj"),
            "bye": (f or {}).get("bye") or (fw or {}).get("bye") or (fl or {}).get("bye"),
            "ros": round(ros, 1),
            "rosRoto": None if ros_r is None else round(ros_r, 1),
            "rosESPN": None if ros_e is None else round(ros_e, 1),
            "rosFP": None if ros_f is None else round(ros_f, 1),
            "rosFlock": None if ros_k is None else round(ros_k, 1),
            "flockRosRank": None if not fl else round(fl["rank"], 3),
            "rosCalc": None if ros_c is None else round(ros_c, 1),
            "calcRosRank": None if not fc else round(fc["rank"], 3),
            "rosDS": None if ros_d is None else round(ros_d, 1),
            "dsRosRank": None if not dsr else round(dsr["rank"], 3),
            "wkDS": None if wk_d is None else round(wk_d, 1),
            "dsWkRank": None if not dsw else round(dsw["rank"], 3),
            "fpRosRank": None if not f else round(f["rank"], 3),
            "wk": round(sum(wparts) / len(wparts), 1) if wparts else None,
            "wkRoto": wk_r,
            "wkESPN": wk_e,
            "wkFP": None if wk_f is None else round(wk_f, 1),
            "wkFlock": None if wk_k is None else round(wk_k, 1),
            "flockWkRank": None if not fk else round(fk["rank"], 3),
            "fpWkRank": None if not fw else round(fw["rank"], 3),
            "opp": (r or {}).get("opp", {}).get(week),
            "deep": deep,
            "sr": stat_sum(r), "se": stat_sum(e), "sw": stat_week(r), "ew": stat_week(e),
            "espnId": ESPN_IDS.get(key) or (fc or {}).get("espnId"),
            "own": None if key not in ESPN_OWN else round(ESPN_OWN[key][0], 1),
            "ownChange": None if key not in ESPN_OWN else round(ESPN_OWN[key][1], 2),
        })

    # Replacement level per position -> value over replacement (used for ranking + trades)
    for pos in POSITIONS:
        pool = sorted((p for p in players if p["pos"] == pos), key=lambda p: (p["deep"], -p["ros"]))
        core = [p for p in pool if not p["deep"]]   # "deep" = rank-only players far below replacement level
        idx = min(REPLACEMENT_RANK[pos], len(core)) - 1
        repl = core[idx]["ros"] if core else 0
        for rank, p in enumerate(pool, 1):
            p["posRank"] = rank
            p["vor"] = round(p["ros"] - repl, 1)   # unclamped value over replacement (can be negative)
            p["value"] = round(max(p["ros"] - repl, 0), 1)
            p["tradeValue"] = round(p["value"] * (QB_TRADE_PREMIUM if pos == "QB" else 1), 1)
    players.sort(key=lambda p: (p["deep"], -p["value"], -p["ros"]))
    for i, p in enumerate(players, 1):
        p["rank"] = i

    return {
        "updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "season": season, "week": week, "lastWeek": LAST_WEEK,
        "scoring": {**{k: 0 for k in STAT_KEYS}, **SCORING, "te_rec_bonus": 0}, "statKeys": STAT_KEYS,
        "flexSplit": FLEX_SPLIT, "benchBuffer": BENCH_BUFFER, "replacementRank": REPLACEMENT_RANK,
        "league": {"teams": TEAMS, "lineup": LINEUP, "qbTradePremium": QB_TRADE_PREMIUM},
        "sources": ["Rotowire projections (re-scored for your league)",
                    "ESPN projections (re-scored for your league)",
                    "FantasyPros expert consensus (ROS + weekly, half-PPR)",
                    "Flock Fantasy expert consensus (superflex redraft + weekly)",
                    "FantasyCalc trade values (redraft, 10-team superflex, 0.5 PPR; ROS only)",
                    "Draft Sharks rankings (ROS + weekly, half-PPR)"],
        "sourceStatus": statuses,
        "players": players,
    }


if __name__ == "__main__":
    data = build()
    OUT.parent.mkdir(exist_ok=True)
    tmp = OUT.with_suffix(".tmp")                  # write then swap, so data.js is never half-written
    tmp.write_text("window.FF_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n", encoding="utf-8")
    os.replace(tmp, OUT)
    print(f"Wrote {len(data['players'])} players -> {OUT}")
    degraded = [s for s in data["sourceStatus"] if s["status"] != "ok"]
    if degraded:
        print("WARNING: " + "; ".join(f"{s['name']} {s['status']}" for s in degraded) + " (the site shows a notice)")
    for p in data["players"][:12]:
        print(f"{p['rank']:>3} {p['name']:<22}{p['pos']} ROS {p['ros']:>6} (roto {p['rosRoto']}, espn {p['rosESPN']}, fp {p['rosFP']}, flock {p['rosFlock']}, calc {p['rosCalc']}, sharks {p['rosDS']}) wk {p['wk']}")
