from wordcloud import WordCloud, STOPWORDS
import matplotlib.pyplot as plt

data = """Lost Worlds: not so lost anymore?
November 17, 2025 by Tipa
I am a terrible person. You’ll agree once you know what I know.

But first… does anyone else find themselves as adults, buying the stuff they couldn’t afford when they were younger? I bet that’s pretty common. See: my Vectrex, and all those games I bought for it.

As a kid, I didn’t have anyone to play D&D with. I’d seen the original books down at Toy City, Concord NH’s much missed toy store at the corner of Pleasant St and Storrs, across the street from the Britt’s shopping center. I’d bought them because, for some reason, probably because I was a kid, I wasn’t aware I needed other people to play. I eventually roped my little sister in for a game, but it wasn’t until I went to college that I found other people with whom to play. Who actually wanted to play.

Even back in the day, D&D wasn’t a cheap buy, and so there were a lot of D&D-adjacent things I just couldn’t afford and had to watch pass on by. All the Judges Guild stuff, all the Tékumel stuff, the Tunnels & Trolls, and especially those play-by-mail games hosted by Flying Buffalo.

Those were awesome (probably) and reminded me of the decidedly non-fantasy game, Diplomacy. You would generate a group of adventurers and would be placed in a dungeon with other groups of adventurers, as well as monsters, traps, treasure and so on. Flying Buffalo would send you a printout stating where you were, what you saw, who (or what) was there with you and so on. You would mark the sheet with what you planned to do (“Fight! Negotiate! Search for Treasure!”) and stuff and mail it back. When all the groups had sent in their moves, the folks at FB would run them all through their Adventuretron 5000, tabulate the results, and send them to you along with the sheet for your next move.

I so wanted to play that.


Ace of Aces
When I saw ads for Flying Buffalo’s “Ace of Aces” World War I air combat game, it looked like black magic to me. You and a friend take on the role of a Red Baron or an Eddie Rickenbacker and take to the skies. One of you would be landing to cheers and champagne. One of you would be landing somewhat short of the runway, probably in flames.

The game was simple to explain, tough to figure out. You both would start at a certain page, with a drawing of the cockpit of the plane as if you were sitting in it. In the distance ahead of you is drawn your enemy. You have a list of maneuvers (represented as arrows generally describing what you want your plane to do) and a page. You would choose a maneuver, turn to the indicated page, and then tell your opponent what maneuver you chose. They do the same. When you both have each other’s maneuver, you look at the row on the page for their maneuver, go to the indicated page, and then you’d find yourself looking at the enemy plane in its new position.

If it was heading right for you, guns blazing, it was not going to be a good day for you.

I couldn’t figure out how it even worked. Magic is real. When my son was living in Virginia, I thought it would be really cool if I bought a set of the books and we could play by e-mail or something. He wasn’t into it. I forced my niece to play a couple of rounds, but after I kept winning, she didn’t want to play anymore. This was the last one the publishers at the time had, btw. They’d had a reprint (that I missed), but this was on their website and I begged to give us a chance, my son and I would really love to play, and they found this one and sent it.

I treasure it.


Lost Worlds list of maneuvers
Ace of Aces was designed by Alfred Leonardi, who, unfortunately, passed away earlier this year. He went on to adapt the Ace of Aces combat system to Star Wars (X-Wing vs TIE Fighter) and to a series of fantasy combat books, the “Lost Worlds” series. Instead of dogfighting maneuvers, the maneuvers were attack and defense actions. Dozens of different fighters were written, all based on the same system. Darth Vader and Luke Skywalker also got books, so… Luke vs a Skeleton with a Scimitar? Yeah, that can happen. Might not go well for the skeleton.

By the time these were released, computer RPGs were a thing, and they didn’t require me hunting up someone to play with, and so I more or less forgot about them.

Until now, that is. Because while Kasul and I were out shopping this weekend, I saw a bunch of these Lost Worlds books at Tabletop Games in Newington (CT). I bought the “Female Warrior with Sword and Chainmail”/”Giant Goblin with Mace and Shield” (actually a morningstar but who cares). In these books, you keep your maneuver card and hand your book to your opponent and they hand you theirs. You’ll see their character standing in front of you, and they’ll see yours.

I tried a solo game, where I would choose my maneuver and I would roll a die for the opponent’s choice. I charged in first thing without a care in the world and it clonked me, right on the head. So when I got Kasul to give it a play, I played far more defensively, knocked him backward with my shield, knocked his weapon out of his hand, and went for the kill and won.

I imagine that’s the last game of that we play, but maybe I can get a few more games out of him.

That’s really the issue with the game in general; there’s not really much there. It’s fun if you use your imagination, but I imagine it’s prone to both players just turtling. If I were going to suggest a change, I would enforce a turn limit, and the winner would be the one who had made the greater number of hits, no matter how severe. If neither had made ANY hits, both would lose. Same number of hits, draw. Penalize turtling.

But here’s where I tell you why I am a terrible person.

This latest round of reprints comes from NOVA Game Designs, led by Leonardi’s daughter, Jill, herself a game designer who has put out a line of “Queen’s Blade” fantasy combat books, of which I was unaware until now. She and two others run the company and completed a Kickstarter last year for a newer Ace of Aces reprint, of which I was also unaware.

But here’s where the plot thickens.


Nova Game Designs LLC, Willimantic, CT
Oh… Nova Games is just up the street. I can and have biked up to Willimantic. They have a cool frog bridge. Wow, that explains how their games ended up at Tabletop. They are in the area. Let’s find out more.

Here it comes.


They were at Silk City Gamers
Willimantic is known as the “Thread City”. Textiles were big industry in New England before the USA sent all manufacturing overseas, pretty much devastating the region and leaving ruins of factories throughout.

Manchester, Connecticut, the town where I live, is nicknamed “Silk City”, due to our homegrown (now dead) particular industry. They’d come to my town, to my library, to play Ace of Aces and chew gum, and no food is allowed in the library. So no gum. They’d be forced to play their games.

Kasul and I knew about this, but it was so close to ConnectiCon that we opted not to go. Clearly, I didn’t know Nova would be there or I would have gone.

It would have been amazing to meet these people, who didn’t know how important they’d been to a geek from New Hampshire back in the day. I’d have told them. I wouldn’t have bought a new copy of Ace of Aces because I like the one I have, but maybe I could have had them sign it or something.

I see how I missed it. I’m not on Facebook, and I am not a member of their board game club, as we play within the family up to two nights a week. I haven’t been to the library for a couple of months since I subbed to Kindle Unlimited and get bunches of books for free through that.

It’s all my fault. All I can do now is buy more of these books, I suppose."""

# All words will be this lighter shade:
WORD_COLOR = "#476B6B"

def subtle_color_func(*args, **kwargs):
    return WORD_COLOR

wc = WordCloud(
    width=240,
    height=160,
    background_color="#2F4F4F",
    color_func=subtle_color_func,
    stopwords=STOPWORDS,
    max_words=200,
    collocations=False
).generate(data)

plt.figure(figsize=(10,5))
plt.imshow(wc, interpolation='bilinear')
plt.axis('off')
plt.show()
wc.to_file('wordcloud.png')
