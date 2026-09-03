"""MilestoneManager: tracks distance achievements."""

milestones = [
    (10000, "International Traveller", "\U0001F30F"),      
    (20000, "World Tour", "\U0001F310"),                  
    (40075, "Around the Globe", "\U0001F30D"),            
    (200375, "5 Times Around the Globe", "\U0001F680"),   
]


class MilestoneManager:
    def __init__(self, achieved=None):
        self.achieved = set(achieved or [])

    def check(self, total_distance_km):
        """Returns a list of (threshold, name, emoji) newly crossed."""
        newly = []
        for threshold, name, emoji in milestones:
            key = str(threshold)
            if total_distance_km >= threshold and key not in self.achieved:
                self.achieved.add(key)
                newly.append((threshold, name, emoji))
        return newly
