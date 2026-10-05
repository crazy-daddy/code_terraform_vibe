# Feed Maker automation: crafts creature feed to the Wildlife
# planner's home stock targets. See lib/feed_maker.py.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import feed_maker as self

from feed_maker import FeedMakerController

FeedMakerController(self).run()
