# DailyBlogroll

DailyBlogroll is a simple Python tool that generates a "daily blogroll"—a curated list of links to gaming and tech blogs you follow. The project is designed to help you keep track of fresh content from your favorite blogs and share daily recommendations.

## Features

- **Automated Blogroll Generation:** Collects and compiles links from blogs you read into a daily list.
- **Customizable Sources:** Easily modify the list of blogs and feeds.
- **Focus on Gaming & Tech:** Tailored for enthusiasts who want up-to-date content in these niches.
- **Deep Dive Supplements:** Publishes an occasional narrative feature when
  enough recent posts converge on one configured topic.
- **Lightweight & Easy to Use:** Minimal dependencies, runs with Python.

## How It Works

The core logic is implemented in [`blogroll.py`](blogroll.py). The script fetches new posts from your configured blogs and assembles them into a daily digest.

To learn more about the details of the workflow, configuration, and blog sources, please refer to the documentation and comments in [`blogroll.py`](blogroll.py).

## Getting Started

### Prerequisites

- Python 3.x

### Installation

Clone the repository:

```sh
git clone https://github.com/tipa16384/dailyblogroll.git
cd dailyblogroll
```

Install any required dependencies (see `blogroll.py` for details):

```sh
pip install -r requirements.txt
```

### Usage

Run the script to generate your daily blogroll:

```sh
python focused_news.py
python blogroll.py
```

`focused_news.py` should run first. It may generate a static HTML Deep Dive, but
does nothing when no topic has enough matching posts. `blogroll.py` then links
the latest completed supplement from the mutable `index.html`; dated Blogroll
archives remain unchanged. See [`FOCUSED_NEWS.md`](FOCUSED_NEWS.md) for topic,
retention, threshold, output, and diagnostic options.

You can customize the included blogs in `feeds.yaml`.

## Configuration

Open `blogroll.py` and look for the section where blog URLs or feeds are defined. Modify this list to include your favorite gaming and tech blogs.

## Contributing

Contributions, bug reports, and feature suggestions are welcome! Feel free to open issues or pull requests.

## License

This project is licensed under the MIT License.

## Author

[@tipa16384](https://github.com/tipa16384)

---

For more details on how the blogroll is generated, refer to [`blogroll.py`](blogroll.py).
