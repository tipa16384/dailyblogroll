from feedgen.feed import FeedGenerator
from blogroll import get_sorted_blogrolls, BLOGROLLS_DIR
from bs4 import BeautifulSoup

def make_feed():
    fg = FeedGenerator()
    fg.id('http://example.com/rss_feed')
    fg.title('Daily Blogroll')
    fg.author({'name': 'Tipa', 'email': 'brendahol@gmail.com'})
    fg.link(href='http://westkarana.xyz', rel='alternate')
    fg.description('Daily Blogroll, now in XML!')
    fg.language('en')

    # get the latest 5 blogrolls
    blog_rolls = get_sorted_blogrolls()[::-1][:5]

    for date_str, blogs in blog_rolls:
        print (f"Date: {date_str}, Blogs: {BLOGROLLS_DIR / blogs}")
        with open(BLOGROLLS_DIR / blogs, 'r', encoding='utf-8') as f:
            html_content = f.read()
            fe = fg.add_entry()

            # get the title from the <head> and use that for id and title
            soup = BeautifulSoup(html_content, 'html.parser')
            title = soup.title.string if soup.title else f"Blogroll for {date_str}"
            fe.id(f"https://westkarana.xyz/{blogs}")
            fe.title(title)
            fe.link(href=f"https://westkarana.xyz/{blogs}", rel='alternate')
            fe.pubDate(pubDate=f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}T00:00:00Z") # Use the date from the filename

            # get a list of all the "div.feed-element" elements
            feed_elements = soup.find_all("div", class_="feed-element")
            print (f"Found {len(feed_elements)} feed elements")
            # each feed element contains two links. Link 1 has class feed-element-image and contains an image. Link 2 has class one-liner
            # and contains text content. We want to extract both links and the image (if present) and put them in the description
            description = ""
            for element in feed_elements:
                image = element.find("img", class_="feed-element-image")
                one_liner = element.find("a", class_="oneliner")
                if image:
                    description += f'<img src="{image["src"]}" alt="{title} image">'
                if one_liner:
                    description += f'<p>{one_liner.text}</p>'
            print (f"Description: {description}")
            fe.description(description)

    # Generate the RSS XML
    rss_feed = fg.rss_str(pretty=True)
    print(rss_feed.decode('utf-8'))

    # Save to a file
    fg.rss_file('rss.xml', pretty=True)

if __name__ == "__main__":
    make_feed()