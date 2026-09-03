"""MilestoneManager: tracks distance achievements."""

MILESTONES = [
    (1, "Local Explorer", "\U0001F5FA️"),       # 🗺️
    (10, "City Traveller", "\U0001F6B6"),             # 🚶
    (42.2, "Mouse Marathon", "\U0001F3C3"),           # 🏃
    (100, "Regional Traveller", "✈️"),      # ✈️
    (1000, "International Traveller", "\U0001F30F"),  # 🌏
    (40075, "Around the Earth!", "\U0001F30D"),       # 🌍
]


class MilestoneManager:
    def __init__(self, achieved=None):
        self.achieved = set(achieved or [])

    def check(self, total_distance_km):
        """Returns a list of (threshold, name, emoji) newly crossed."""
        newly = []
        for threshold, name, emoji in MILESTONES:
            key = str(threshold)
            if total_distance_km >= threshold and key not in self.achieved:
                self.achieved.add(key)
                newly.append((threshold, name, emoji))
        return newly
