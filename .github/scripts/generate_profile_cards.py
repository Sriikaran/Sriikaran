"""Render GitHub profile cards using the GitHub CLI and the Python standard library."""

import subprocess
import sys
from collections import Counter
from datetime import date, timedelta
from html import escape
from json import loads
from pathlib import Path


REPOSITORIES = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER,
                 privacy: PUBLIC, isFork: false) {
      nodes { primaryLanguage { name } }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

CALENDAR = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date weekday contributionLevel } }
      }
    }
  }
}
"""

WIDTH = 760
ASSETS = Path(__file__).resolve().parents[2] / "assets"
MUTED = "#abbad0"
ACCENTS = ("#72dfb2", "#89baff", "#ecbf78", "#b4aaff", "#9edce9")
HEAT = {
    "NONE": "#263348",
    "FIRST_QUARTILE": "#204c42",
    "SECOND_QUARTILE": "#337960",
    "THIRD_QUARTILE": "#51b58a",
    "FOURTH_QUARTILE": "#88e5bd",
}


def query(login, document, cursor=None):
    command = ["gh", "api", "graphql", "-f", f"query={document}", "-f", f"login={login}"]
    if cursor is not None:
        command.extend(["-f", f"cursor={cursor}"])
    response = loads(subprocess.check_output(command, encoding="utf-8"))
    if response.get("errors") or not response.get("data", {}).get("user"):
        raise RuntimeError(f"GitHub returned no user data for {login}")
    return response["data"]["user"]


def public_repositories(login):
    page = query(login, REPOSITORIES)["repositories"]
    repositories = list(page["nodes"])
    while page["pageInfo"]["hasNextPage"]:
        page = query(login, REPOSITORIES, page["pageInfo"]["endCursor"])["repositories"]
        repositories.extend(page["nodes"])
    return repositories


def label(x, y, value, *, size=16, fill="#eef5ff", weight=400, anchor="start"):
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" '
        f'font-weight="{weight}" text-anchor="{anchor}">{escape(str(value))}</text>'
    )


def rect(x, y, width, height, fill, *, radius=0, stroke="none"):
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
        f'rx="{radius}" fill="{fill}" stroke="{stroke}"/>'
    )


def card(title, description, height, items):
    body = "\n    ".join(items)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}"
     width="{WIDTH}" height="{height}" role="img" aria-labelledby="title description">
  <title id="title">{escape(title)}</title>
  <desc id="description">{escape(description)}</desc>
  {rect(0.5, 0.5, WIDTH - 1, height - 1, "#151d2a", radius=8, stroke="#344459")}
  <g font-family="ui-monospace, Consolas, monospace">
    {body}
  </g>
</svg>
'''


def stats_card(repositories, total, active_days):
    metrics = [
        ("Original repos", len(repositories)),
        ("Contributions / yr", total),
        ("Active days / yr", active_days),
    ]
    items = [rect(x, 15, 1, 52, "#344459") for x in (254, 508)]
    for index, (name, count) in enumerate(metrics):
        x = 22 + index * 254
        items.append(label(x, 40, f"{count:,}", size=28, fill=ACCENTS[index], weight=700))
        items.append(label(x, 62, name, size=17, fill=MUTED))
    summary = ", ".join(f"{count:,} {name.lower()}" for name, count in metrics)
    return card("Profile overview", summary, 82, items)


def language_card(repositories):
    languages = Counter(
        repo["primaryLanguage"]["name"] for repo in repositories if repo["primaryLanguage"]
    )
    title = "Repository languages"
    items = [label(20, 30, title, size=21, weight=700)]
    items.append(label(740, 30, "Primary language per original repo", size=13, fill=MUTED, anchor="end"))
    if not languages:
        items.append(label(20, 64, "No detected languages", fill=MUTED))
        return card(title, "No detected languages", 86, items)

    top_languages = sorted(languages.items(), key=lambda item: (-item[1], item[0]))[:5]
    total = sum(languages.values())
    for index, (name, count) in enumerate(top_languages):
        y = 62 + index * 23
        color = ACCENTS[index]
        share = count / total
        items.append(label(20, y, name, size=15, weight=600))
        items.append(rect(170, y - 10, 516, 10, "#233043", radius=5))
        items.append(rect(170, y - 10, round(516 * share), 10, color, radius=5))
        items.append(label(740, y, f"{share:.0%}", size=14, fill=MUTED, anchor="end"))
    summary = ", ".join(f"{name} {count / total:.0%}" for name, count in top_languages)
    return card(title, summary, 62 + len(top_languages) * 23 - 4, items)


def activity_metrics(calendar):
    active_by_week = [
        [date.fromisoformat(day["date"]) for day in week["contributionDays"]
         if day["contributionLevel"] != "NONE"]
        for week in calendar["weeks"]
    ]
    active = sorted(day for week in active_by_week for day in week)
    one_day = timedelta(days=1)
    previous = None
    run = longest = 0
    for day in active:
        run = run + 1 if previous == day - one_day else 1
        longest = max(longest, run)
        previous = day
    return len(active), sum(bool(week) for week in active_by_week), longest


def activity_card(calendar, active_weeks, longest):
    total = calendar["totalContributions"]
    items = [label(20, 30, "Past 12 months", size=20, fill=ACCENTS[0], weight=700)]
    items.append(rect(560, 18, 1, 134, "#344459"))
    items.append(label(580, 40, "Active weeks", size=15, fill=MUTED))
    items.append(label(580, 65, active_weeks, size=22, weight=700))
    items.append(label(580, 100, "Longest streak", size=15, fill=MUTED))
    streak_label = f"{longest} day" if longest == 1 else f"{longest} days"
    items.append(label(580, 125, streak_label, size=22, weight=700))

    previous_month = None
    months = []
    for column, week in enumerate(calendar["weeks"]):
        days = week["contributionDays"]
        if not days:
            continue
        x = 20 + column * 10
        week_start = date.fromisoformat(days[0]["date"])
        if week_start.month != previous_month:
            months.append((x, week_start.strftime("%b")))
            previous_month = week_start.month
        for day in days:
            y = 61 + day["weekday"] * 11
            items.append(rect(x, y, 8, 8, HEAT[day["contributionLevel"]], radius=1))

    if len(months) > 1 and months[1][0] - months[0][0] < 25:
        months.pop(0)
    for x, month in months:
        if x < 524:
            items.append(label(x, 52, month, size=11, fill=MUTED))

    items.append(label(20, 153, "Less", size=11, fill=MUTED))
    for index, color in enumerate(HEAT.values()):
        items.append(rect(52 + index * 11, 145, 8, 8, color, radius=1))
    items.append(label(111, 153, "More", size=11, fill=MUTED))
    description = (f"{total:,} contributions over the past year. Active weeks: {active_weeks}. "
                   f"Longest streak in the past year: {streak_label}.")
    return card("Contribution activity", description, 170, items)


def main(login):
    repositories = public_repositories(login)
    calendar = query(login, CALENDAR)["contributionsCollection"]["contributionCalendar"]
    active_days, active_weeks, longest = activity_metrics(calendar)
    cards = {
        "stats": stats_card(repositories, calendar["totalContributions"], active_days),
        "languages": language_card(repositories),
        "activity": activity_card(calendar, active_weeks, longest),
    }
    ASSETS.mkdir(exist_ok=True)
    for name, svg in cards.items():
        (ASSETS / f"profile-{name}.svg").write_text(svg, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main(sys.argv[1])
