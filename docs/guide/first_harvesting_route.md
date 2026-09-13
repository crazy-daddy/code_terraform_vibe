# Guide: first_harvesting_route

## First Harvesting Route

Harvesting is the most direct early path into visible machine automation. It can earn more than manual Biology, while keeping the first working version much smaller than a reliable automated Biology chain.

### What you are building

A useful harvesting route usually has three parts: choose where to go, collect material, then store and sell when Inventory says it is time. The main decision is not the individual call; it is deciding when to move on.

### What to inspect

Read the Harvester Info tab first. Then check the Scanner and Harvester entries in DOCS. The Scanner teaches what is known about the surface. The Harvester teaches movement, collection, heat, and the held-item slot.

### Keep the first route simple

You do not need pathfinding. A fixed sweep across adjacent grid cells can collect and store everything it finds. Check heat before moving, handle the held item before collecting again, and optimize the route only after the basic loop works.

### A good first target

Start with one short trip that reaches a known area, collects something, stores it, and leaves it ready to sell from Inventory. Then extend the sweep or add smarter choices.

*Guide / Tutorials*

---
