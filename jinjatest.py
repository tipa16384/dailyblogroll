from jinja2 import Environment, PackageLoader, select_autoescape
env = Environment(
    loader=PackageLoader("jinjatest"),
    autoescape=select_autoescape()
)

def main():
    template = env.get_template("newspapertemplate.html")

    jinja_vars = {}
    jinja_item_list = []
    jinja_vars['title'] = "My Blogroll"
    jinja_vars['previous'] = "page1.html"
    jinja_vars['next'] = "page3.html"
    jinja_vars['date'] = "2024-06-15"

    item = {}
    item['name'] = "Example Blog"
    item['url'] = "https://chasingdings.com"
    item['image'] = "images/303118891c325ea66b90a1409e3c9a44a16f48d4458d738ed0cb05a1e09852bc.png"
    item['one_liner'] = "This is an example blog."
    jinja_item_list.append(item)


    item = {}
    item['name'] = "Example Blog 2"
    item['url'] = "https://chasingdings.com"
    item['image'] = "images/303118891c325ea66b90a1409e3c9a44a16f48d4458d738ed0cb05a1e09852bc.png"
    item['one_liner'] = "This is an example blog. This is a large amount of text to test how the layout handles larger blocks of text within the one-liner section of the blog item. It should properly wrap and display without breaking the design."
    jinja_item_list.append(item)


    item = {}
    item['name'] = "Example Blog 3"
    item['url'] = "https://chasingdings.com"
    item['image'] = "images/303118891c325ea66b90a1409e3c9a44a16f48d4458d738ed0cb05a1e09852bc.png"
    item['one_liner'] = "Random text for blog 3. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua."
    jinja_item_list.append(item)


    item = {}
    item['name'] = "Example Blog 4"
    item['url'] = "https://chasingdings.com"
    item['image'] = "images/303118891c325ea66b90a1409e3c9a44a16f48d4458d738ed0cb05a1e09852bc.png"
    item['one_liner'] = "Random text for blog 4. Lorem ipsum dolor sit amet. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua."
    jinja_item_list.append(item)


    item = {}
    item['name'] = "Example Blog 5"
    item['url'] = "https://chasingdings.com"
    item['image'] = "images/303118891c325ea66b90a1409e3c9a44a16f48d4458d738ed0cb05a1e09852bc.png"
    item['one_liner'] = "Random text for blog 5. Lorem ipsum dolor sit amet. Blah blah blah. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua."
    jinja_item_list.append(item)


    item = {}
    item['name'] = "Example Blog 6"
    item['url'] = "https://chasingdings.com"
    item['image'] = "images/303118891c325ea66b90a1409e3c9a44a16f48d4458d738ed0cb05a1e09852bc.png"
    item['one_liner'] = "Random text for blog 6. The quick brown fox jumps over the lazy dog. Lorem ipsum dolor sit amet, consectetur adipiscing elit."
    jinja_item_list.append(item)

    item = {}
    item['name'] = "Example Blog 7"
    item['url'] = "https://chasingdings.com"
    item['image'] = "images/303118891c325ea66b90a1409e3c9a44a16f48d4458d738ed0cb05a1e09852bc.png"
    item['one_liner'] = "Random text for blog 7. Thus was spake the seventh blog in the list of examples."
    jinja_item_list.append(item)

    item = {}
    item['name'] = "Example Blog 8"
    item['url'] = "https://chasingdings.com"
    item['image'] = "images/303118891c325ea66b90a1409e3c9a44a16f48d4458d738ed0cb05a1e09852bc.png"
    item['one_liner'] = "Random text for blog 8. Thus was spake the eighth blog in the list of examples. Three more to go!"
    jinja_item_list.append(item)

    item = {}
    item['name'] = "Example Blog 9"
    item['url'] = "https://chasingdings.com"
    item['image'] = "images/303118891c325ea66b90a1409e3c9a44a16f48d4458d738ed0cb05a1e09852bc.png"
    item['one_liner'] = "Random text for blog 9. Thus was spake the ninth blog in the list of examples. Two more to go!"
    jinja_item_list.append(item)

    item = {}
    item['name'] = "Example Blog 10"
    item['url'] = "https://chasingdings.com"
    item['image'] = "images/303118891c325ea66b90a1409e3c9a44a16f48d4458d738ed0cb05a1e09852bc.png"
    item['one_liner'] = "Random text for blog 10. Thus was spake the tenth blog in the list of examples. One more to go!"
    jinja_item_list.append(item)

    item = {}
    item['name'] = "Example Blog 11"
    item['url'] = "https://chasingdings.com"
    item['image'] = "images/303118891c325ea66b90a1409e3c9a44a16f48d4458d738ed0cb05a1e09852bc.png"
    item['one_liner'] = "Random text for blog 11. Thus was spake the eleventh blog in the list of examples. This is the last one!"
    jinja_item_list.append(item)

    jinja_vars['blogs'] = jinja_item_list

    output = template.render(vars=jinja_vars)

    with open("docs/output.html", "w") as f:
        f.write(output)

if __name__ == "__main__":
    main()
