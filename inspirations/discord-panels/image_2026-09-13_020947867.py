outpost = get_component("outpost_home")

powerList = [0] * 24
clock = get_component("clock")
labels = [0] * 24

daytime = {"dawn":6, "day":7, "dusk":18, "night":20}

for i in range(24):
  labels[i] = i

while True:
  panel.clear()
  hour = clock.get_time()[0]
  labels[hour] = f"{hour}!"
  if hour:
    labels[hour - 1] = hour - 1
  else:
    labels[23] = 23
  batteries = [get_component(b.id) for b in outpost.buildings("battery")]
  maxPower = 0
  power = 0
  for b in batteries:
    maxPower += b.get_capacity()
    power += b.get_level()
  powerList[hour] = power

  barVPosition = (panel.height() / 50) * 47
  panel.fill_rect((daytime["dawn"] / 24) * panel.width(), barVPosition, (1 / 24) * panel.width(), panel.height(), "#444534")
  panel.fill_rect((daytime["day"] / 24) * panel.width(), barVPosition, (11 / 24) * panel.width(), panel.height(), "#727819")
  panel.fill_rect((daytime["dusk"] / 24) * panel.width(), barVPosition, (2 / 24) * panel.width(), panel.height(), "#0d0a4d")
  
  panel.bar_chart(0, 0, panel.width(), panel.height(), powerList, maxPower, labels)
  labelText = f"{int(power)} / {maxPower} Wh"
  
  time = clock.get_time()
  time[0] = time[0] < 10 and f"0{time[0]}" or time[0]
  time[1] = time[1] < 10 and f"0{time[1]}" or time[1]
  subText = f"{time[0]}:{time[1]}"
  panel.counter(panel.width() / 2, panel.height() / 2, subText, labelText)