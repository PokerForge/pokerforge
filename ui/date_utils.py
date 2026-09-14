"""Period filtering, ported from poker_dashboard_legacy.py's date_range()
(pure date logic, no DB dependency) plus an "All Time" option."""
import calendar
from datetime import date, timedelta

PERIODS = ["All Time", "Today", "Yesterday", "Last Week", "This Week", "This Month",
           "Last Month", "Last 3 Months", "Last 6 Months", "This Year", "Last Year"]

# Appended separately (not part of PERIODS) since it isn't a fixed range
# date_range() can compute on its own — selecting it in the UI opens a
# calendar picker instead.
CUSTOM_RANGE_LABEL = "Custom Range..."


def _months_ago(d: date, months: int) -> date:
    """`d`, `months` calendar-months earlier — clamped to the target
    month's actual length (e.g. Mar 31 minus 1 month -> Feb 28/29) rather
    than overflowing into the following month the way naive day-math
    would."""
    month = d.month - months
    year = d.year
    while month <= 0:
        month += 12
        year -= 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def date_range(period):
    today = date.today()
    if period == "All Time":       return date(2000, 1, 1), today
    if period == "Today":          return today, today
    if period == "Yesterday":      y = today - timedelta(1); return y, y
    if period == "Last Week":      return today - timedelta(7), today
    if period == "This Week":      return today - timedelta((today.weekday() + 1) % 7), today
    if period == "This Month":     return date(today.year, today.month, 1), today
    if period == "Last Month":
        f = date(today.year, today.month, 1) - timedelta(1)
        return date(f.year, f.month, 1), f
    if period == "Last 3 Months":  return _months_ago(today, 3), today
    if period == "Last 6 Months":  return _months_ago(today, 6), today
    if period == "This Year":      return date(today.year, 1, 1), today
    if period == "Last Year":      return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    return date(2000, 1, 1), today


def month_range(year: int, month: int) -> tuple[date, date]:
    """First and last day of the given calendar month."""
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)
