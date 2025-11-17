from blogroll import load_cfg
import csv

fn = 'demographics.csv'

def main():
    cfg = load_cfg()
    feed_dict = {}
    blogger_data = {}
    for feed in cfg['feeds']:
        blogger = feed.get('blogger', None)
        if not blogger:
            continue
        if not feed.get('skip', False):
            if not blogger in feed_dict:
                feed_dict[blogger] = []
            feed_dict[blogger].append(feed)
    for blogger, feeds in feed_dict.items():
        data = {}
        data['Name'] = blogger
        data['Blog'] = ', '.join([f['name'] for f in feeds])
        pronouns_list = [f.get('pronouns', None) for f in feeds if 'pronouns' in f]
        if any('she' in p for p in pronouns_list):
            data['Gender'] = 'Female'
        elif any('him' in p for p in pronouns_list):
            data['Gender'] = 'Male'
        else:
            data['Gender'] = 'Other'
        blogger_data[blogger] = data
    with open(fn, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Name', 'Blog', 'Gender']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for data in blogger_data.values():
            writer.writerow(data)

if __name__ == '__main__':
    main()