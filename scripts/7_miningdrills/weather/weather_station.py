# Weather Station: decodes storm aftermath coordinates (Raw Uranium, Storm Glass)
# from every station's receiver into weather.aftermaths. Only the lowest-id powered
# station keeps running; the others end at once. See lib/weather_signals.py.

from weather_signals import WeatherController

WeatherController(self).run()
