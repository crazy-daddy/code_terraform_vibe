# Weather Station Automation Script
# Continuously monitors planetary temperature, pressure, oxygen and dust storm activity
print(f"[Weather Station] {self.name} online.")

while True:
    try:
        data = {
            "temp": getattr(self, "temperature", None),
            "pressure": getattr(self, "pressure", None),
            "oxygen": getattr(self, "oxygen", None),
            "storm": getattr(self, "storm_active", False),
        }
        # Update shared archive telemetry
        archive[f"weather.{self.name}"] = data
    except Exception:
        pass
    sleep(10.0)

