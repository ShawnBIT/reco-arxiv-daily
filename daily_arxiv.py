import os
import re
import json
import arxiv
import yaml
from urllib.parse import quote
import logging
import argparse
import datetime
import requests

logging.basicConfig(format='[%(asctime)s %(levelname)s] %(message)s',
                    datefmt='%m/%d/%Y %H:%M:%S',
                    level=logging.INFO)

github_url = "https://api.github.com/search/repositories"
arxiv_url = "http://arxiv.org/"

def load_config(config_file:str) -> dict:
    '''
    config_file: input config file path
    return: a dict of configuration
    '''
    # make filters pretty: only search in title and abstract (ti: / abs:); optional cat: subject
    def pretty_filters(**config) -> dict:
        keywords = dict()
        EXCAPE = '\"'
        OR = ' OR '
        subject = (config.get('subject_category') or '').strip()
        def parse_filters(filters: list) -> str:
            parts = []
            for f in filters:
                if len(f.split()) > 1:
                    term = EXCAPE + f + EXCAPE
                else:
                    term = f
                parts.append(f'(ti:{term} OR abs:{term})')
            q = OR.join(parts)
            if subject:
                q = f'cat:{subject} AND ({q})'
            return q
        for k, v in config['keywords'].items():
            keywords[k] = parse_filters(v['filters'])
        return keywords
    with open(config_file,'r') as f:
        config = yaml.load(f,Loader=yaml.FullLoader)
        config['kv'] = pretty_filters(**config)
        logging.info(f'config = {config}')
    return config

def get_authors(authors, first_author = False):
    output = str()
    if first_author == False:
        output = ", ".join(str(author) for author in authors)
    else:
        output = authors[0]
    return output

def sort_papers(papers):
    output = dict()
    keys = list(papers.keys())
    keys.sort(reverse=True)
    for key in keys:
        output[key] = papers[key]
    return output

def extract_title_from_row(row: str) -> str:
    """从存储的表格行中解析出标题（第二列，可能带 **）"""
    if not row or not row.strip():
        return ''
    parts = row.split("|")
    if len(parts) < 3:
        return ''
    return parts[2].strip().strip('*').strip()

def normalize_table_row(s: str) -> str:
    """将存储的表格行统一为 4 列：Date|Title|Authors|PDF（兼容旧格式含 Affiliation 或 Code 的行）"""
    if not s or not s.strip():
        return s
    parts = s.split("|")
    if len(parts) < 4:
        return s
    date = parts[1].strip().strip('*')
    title = parts[2].strip().strip('*')
    authors = parts[3].strip()
    # 新格式 5 列: date|title|authors|affiliation|link；旧 5 列: date|title|authors|link|code；目标 4 列
    if len(parts) > 5 and parts[5].strip().startswith('['):
        link = parts[5].strip()
    elif len(parts) > 4 and parts[4].strip().startswith('['):
        link = parts[4].strip()
    else:
        link = parts[4].strip() if len(parts) > 4 else ''
    return "|**{}**|**{}**|{}|{}|\n".format(date, title, authors, link)

# 主 README 论文类型标签：GitHub 会 strip 掉所有 style，只能用图片显色。用 shields.io 徽章 + <img width> 在 GitHub 上可读且有色
SHIELDS_BASE = "https://img.shields.io/badge"
DEFAULT_TAG_WIDTH = 200  # 未在 PAPER_TAG_WIDTHS 中指定时的默认宽度
PAPER_TAG_STYLES = {
    "GR": "1e5c3a",       # 青灰绿
    "LLM": "2c4a78",      # 雾蓝
    "Scaling": "8b5a3c",  # 陶土
    "Seq": "5a4a6a",      # 雾紫
    "Other": "5a5a5a",    # 中性灰
}
# 每个 Tag 的徽章显示宽度（px）。短标签只设 width 不设 height，保持比例避免上下压缩感
PAPER_TAG_WIDTHS = {
    "GR": 56,
    "LLM": 56,
    "Scaling": 200,
    "Seq": 56,
    "Other": 120,
}

def get_paper_tag(title: str, tag_rules: list) -> str:
    """按配置规则根据标题匹配论文类型，顺序优先，未匹配为最后一项（Other）。"""
    if not title or not tag_rules:
        return tag_rules[-1]["label"] if tag_rules else "Other"
    t = title.lower()
    for rule in tag_rules:
        words = rule.get("words") or []
        if not words:
            continue
        if any(w.lower() in t for w in words):
            return rule["label"]
    return tag_rules[-1]["label"] if tag_rules else "Other"

def format_row_with_tag(row_str: str, tag_label: str, tag_styles: dict) -> str:
    """将 4 列表格行扩展为 5 列，在 Title 与 Authors 之间插入带颜色的 Tag 列。"""
    if not row_str or not row_str.strip():
        return row_str
    parts = row_str.split("|")
    if len(parts) < 4:
        return row_str
    date = parts[1].strip().strip('*')
    title = parts[2].strip().strip('*')
    authors = parts[3].strip()
    if len(parts) > 5 and parts[5].strip().startswith('['):
        link = parts[5].strip()
    elif len(parts) > 4 and parts[4].strip().startswith('['):
        link = parts[4].strip()
    else:
        link = parts[4].strip() if len(parts) > 4 else ''
    color = tag_styles.get(tag_label, "5a5a5a")
    if isinstance(color, (list, tuple)):
        color = (color[0] or "5a5a5a").lstrip("#")
    else:
        color = str(color).lstrip("#")
    label_enc = quote(tag_label)
    badge_url = f"{SHIELDS_BASE}/-{label_enc}-{color}?style=flat-square&color=%23{color}"
    width = PAPER_TAG_WIDTHS.get(tag_label, DEFAULT_TAG_WIDTH)
    tag_cell = f'<img src="{badge_url}" width="{width}" alt="{tag_label}" />'
    return "|**{}**|**{}**|{}|{}|{}|\n".format(date, title, tag_cell, authors, link)

import requests

def get_code_link(qword:str) -> str:
    """
    This short function was auto-generated by ChatGPT.
    I only renamed some params and added some comments.
    @param qword: query string, eg. arxiv ids and paper titles
    @return paper_code in github: string, if not found, return None
    """
    # query = f"arxiv:{arxiv_id}"
    query = f"{qword}"
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc"
    }
    r = requests.get(github_url, params=params)
    results = r.json()
    code_link = None
    if results["total_count"] > 0:
        code_link = results["items"][0]["html_url"]
    return code_link

def get_daily_papers(topic,query="slam", max_results=2):
    """
    @param topic: str
    @param query: str
    @return paper_with_code: dict
    """
    # output
    content = dict()
    content_to_web = dict()
    search_engine = arxiv.Search(
        query = query,
        max_results = max_results,
        sort_by = arxiv.SortCriterion.SubmittedDate
    )

    for result in search_engine.results():

        paper_id            = result.get_short_id()
        paper_title         = result.title
        paper_url           = result.entry_id
        paper_abstract      = result.summary.replace("\n"," ")
        paper_authors       = get_authors(result.authors)
        paper_first_author  = get_authors(result.authors, first_author=True)
        primary_category    = result.primary_category
        publish_time        = result.published.date()
        update_time         = result.updated.date()
        comments            = result.comment

        logging.info(f"Time = {update_time} title = {paper_title} author = {paper_first_author}")

        # eg: 2108.09112v1 -> 2108.09112
        ver_pos = paper_id.find('v')
        if ver_pos == -1:
            paper_key = paper_id
        else:
            paper_key = paper_id[0:ver_pos]
        paper_url = arxiv_url + 'abs/' + paper_key

        # 表格列：Publish Date | Title | Authors | PDF
        content[paper_key] = "|**{}**|**{}**|{} et.al.|[{}]({})|\n".format(
               update_time, paper_title, paper_first_author, paper_key, paper_url)
        content_to_web[paper_key] = "- {}, **{}**, {} et.al., Paper: [{}]({})".format(
               update_time, paper_title, paper_first_author, paper_url, paper_url)

        # TODO: select useful comments
        comments = None
        if comments != None:
            content_to_web[paper_key] += f", {comments}\n"
        else:
            content_to_web[paper_key] += f"\n"

    data = {topic:content}
    data_web = {topic:content_to_web}
    return data,data_web


def write_daily_new_md(md_path: str, data_collector: list, config: dict) -> None:
    """
    将本次抓取得到的增量论文（data_collector）写入单独的 daily_new.md，方便查看「今天新增」。
    不依赖历史 JSON，只基于当前一次调用 get_daily_papers 的结果。
    """
    # 汇总本次抓取到的所有 topic -> {paper_id: row}
    papers_by_topic: dict = {}
    for data in data_collector or []:
        for topic, papers in (data or {}).items():
            if not papers:
                continue
            if topic not in papers_by_topic:
                papers_by_topic[topic] = {}
            papers_by_topic[topic].update(papers)

    # 始终写出文件，哪怕本次没有新增，避免 workflow 提交时报 pathspec 错误
    DateNow = datetime.date.today()
    DateNowStr = str(DateNow).replace('-', '.')
    allowed_keywords = list((config.get('keywords') or {}).keys())
    tag_rules = config.get('paper_tags')

    with open(md_path, "w") as f:
        f.write("## Daily New Papers\n")
        f.write(f"> Updated on {DateNowStr}\n\n")

        if not papers_by_topic:
            f.write("_No new papers collected in this run._\n")
            return

        # 按 config 中 keywords 的顺序输出 topic
        for topic in allowed_keywords:
            topic_papers = papers_by_topic.get(topic) or {}
            if not topic_papers:
                continue

            f.write(f"## {topic}\n\n")
            if tag_rules:
                f.write("|Publish Date|Title|Tag|Authors|PDF|\n")
                f.write("|---|---|---|---|---|\n")
            else:
                f.write("|Publish Date|Title|Authors|PDF|\n")
                f.write("|---|---|---|---|\n")

            # 复用主逻辑中的排序与打标签能力
            sorted_topic_papers = sort_papers(topic_papers)
            for _, row in sorted_topic_papers.items():
                if row is None:
                    continue
                if tag_rules:
                    title = extract_title_from_row(row)
                    tag = get_paper_tag(title, tag_rules)
                    line = format_row_with_tag(row, tag, PAPER_TAG_STYLES)
                else:
                    # row 本身就是 4 列表格行，直接写出
                    line = row
                f.write(line)
            f.write("\n")

def update_paper_links(filename):
    '''
    weekly update paper links in json file
    '''
    def parse_arxiv_string(s):
        parts = s.split("|")
        date = parts[1].strip().strip('*')
        title = parts[2].strip().strip('*')
        authors = parts[3].strip()
        # 5 列旧格式: date|title|authors|affiliation|link 或 date|title|authors|link|code；目标 4 列
        if len(parts) > 5 and parts[5].strip().startswith('['):
            link = parts[5].strip()
        elif len(parts) > 4 and parts[4].strip().startswith('['):
            link = parts[4].strip()
        else:
            link = parts[4].strip() if len(parts) > 4 else ''
        return date, title, authors, link

    with open(filename, "r") as f:
        content = f.read()
        if not content:
            m = {}
        else:
            m = json.loads(content)

    json_data = m.copy()

    for keywords, v in json_data.items():
        logging.info(f'keywords = {keywords}')
        for paper_id, contents in v.items():
            contents = str(contents)
            update_time, paper_title, paper_first_author, link = parse_arxiv_string(contents)
            contents = "|**{}**|**{}**|{}|{}|\n".format(
                update_time, paper_title, paper_first_author, link)
            json_data[keywords][paper_id] = str(contents)
            logging.info(f'paper_id = {paper_id}, contents = {contents}')
    with open(filename, "w") as f:
        json.dump(json_data, f)

def update_json_file(filename, data_dict):
    '''
    daily update json file using data_dict
    '''
    if os.path.exists(filename):
        with open(filename, "r") as f:
            content = f.read()
            if not content:
                m = {}
            else:
                m = json.loads(content)
    else:
        os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
        m = {}

    json_data = m.copy()

    # update papers in each keywords
    for data in data_dict:
        for keyword in data.keys():
            papers = data[keyword]

            if keyword in json_data.keys():
                json_data[keyword].update(papers)
            else:
                json_data[keyword] = papers

    with open(filename,"w") as f:
        json.dump(json_data,f)

def json_to_md(filename, md_filename,
               task='',
               to_web=False,
               use_title=True,
               use_tc=True,
               show_badge=True,
               use_b2t=True,
               badge_user_name='Vincentqyw',
               badge_repo_name='reco-arxiv-daily',
               allowed_keywords=None,
               paper_tags=None):
    """
    @param filename: str
    @param md_filename: str
    @return None
    """
    def pretty_math(s:str) -> str:
        ret = ''
        match = re.search(r"\$.*\$", s)
        if match == None:
            return s
        math_start,math_end = match.span()
        space_trail = space_leading = ''
        if s[:math_start][-1] != ' ' and '*' != s[:math_start][-1]: space_trail = ' '
        if s[math_end:][0] != ' ' and '*' != s[math_end:][0]: space_leading = ' '
        ret += s[:math_start]
        ret += f'{space_trail}${match.group()[1:-1].strip()}${space_leading}'
        ret += s[math_end:]
        return ret

    DateNow = datetime.date.today()
    DateNow = str(DateNow)
    DateNow = DateNow.replace('-','.')

    with open(filename,"r") as f:
        content = f.read()
        if not content:
            data = {}
        else:
            data = json.loads(content)

    # clean README.md if daily already exist else create it
    with open(md_filename,"w+") as f:
        pass

    # write data into README.md
    with open(md_filename,"a+") as f:

        if (use_title == True) and (to_web == True):
            f.write("---\n" + "layout: default\n" + "---\n\n")

        # if show_badge == True:
        #     f.write(f"[![Contributors][contributors-shield]][contributors-url]\n")
        #     f.write(f"[![Forks][forks-shield]][forks-url]\n")
        #     f.write(f"[![Stargazers][stars-shield]][stars-url]\n")
        #     f.write(f"[![Issues][issues-shield]][issues-url]\n\n")

        if use_title == True:
            #f.write(("<p align="center"><h1 align="center"><br><ins>CV-ARXIV-DAILY"
            #         "</ins><br>Automatically Update CV Papers Daily</h1></p>\n"))
            f.write("## Updated on " + DateNow + "\n")
        else:
            f.write("> Updated on " + DateNow + "\n")

        # TODO: add usage
        f.write("> Usage instructions: [here](./docs/README.md#usage)\n\n")

        # 只输出 config 中配置的主题（allowed_keywords）；若未传则输出 JSON 中全部
        keys_order = list(allowed_keywords) if allowed_keywords else list(data.keys())
        keys_to_show = [k for k in keys_order if k in data and data[k]]

        # 主 README + paper_tags 时：统计五类 Tag 数量并输出 Mermaid 饼图（置顶、直接展示、配色与下方 Tag 一致）
        if paper_tags and to_web == False and keys_to_show:
            tag_counts = {}
            all_dates = []  # 从每行解析出的日期 YYYY-MM-DD
            for keyword in keys_to_show:
                day_content = data.get(keyword) or {}
                day_content = sort_papers(day_content)
                for _, v in day_content.items():
                    if v is None:
                        continue
                    parts = v.split("|")
                    if len(parts) >= 2:
                        d = parts[1].strip().strip("*").strip()
                        if d and re.match(r"\d{4}-\d{2}-\d{2}", d):
                            all_dates.append(d)
                    title = extract_title_from_row(v)
                    tag = get_paper_tag(title, paper_tags)
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
            total_papers = sum(tag_counts.values())
            min_date = min(all_dates) if all_dates else ""
            # 按数量降序，使 Mermaid 饼图切片顺序与配色 pie1..pie5 一致
            tag_order = [r["label"] for r in paper_tags]
            sorted_items = sorted(
                [(l, tag_counts.get(l, 0)) for l in tag_order],
                key=lambda x: -x[1]
            )
            colors_hex = {l: "#" + PAPER_TAG_STYLES.get(l, "5a5a5a").lstrip("#") for l in tag_order}
            f.write("### 📊 Paper distribution by tag\n\n")
            f.write("```mermaid\n")
            f.write("%%{init: {'theme':'base', 'themeVariables': {\n")
            for i, (label, _) in enumerate(sorted_items, 1):
                c = colors_hex.get(label, "#5a5a5a")
                f.write(f"  'pie{i}':'{c}',\n")
            f.write("  'pieTitleTextColor':'#ffffff',\n")
            f.write("  'pieSectionTextColor':'#ffffff',\n")
            f.write("  'pieLegendTextColor':'#ffffff'\n")
            f.write("}}}%%\n")
            f.write("pie showData\ntitle Paper Distribution by Tag\n")
            for label, cnt in sorted_items:
                f.write(f'  "{label}" : {cnt}\n')
            f.write("```\n\n")
            f.write(f"> 统计自 **{min_date}** 起，共计 **{total_papers}** 篇论文。\n\n")

        #Add: table of contents（带样式）
        if use_tc == True:
            f.write('<details style="margin: 1em 0; padding: 0.75em 1em; border: 1px solid #d8dee4; border-radius: 8px; background: #f6f8fa;">\n')
            f.write('  <summary style="cursor: pointer; font-weight: 600; font-size: 1.05em; color: #1f2328; padding: 0.25em 0;">📑 Table of Contents</summary>\n')
            f.write('  <ul style="list-style: none; padding-left: 0; margin: 0.75em 0 0 0; border-top: 1px solid #d8dee4; padding-top: 0.5em;">\n')
            for keyword in keys_to_show:
                # 与 GitHub 标题 ID 一致：小写、空格改 -、只保留字母数字与 -_（/ 被移除，不合并连续 -）
                raw = keyword.lower().replace(' ', '-')
                anchor = ''.join(c for c in raw if c.isalnum() or c in '-_').strip('-')
                f.write(f'    <li style="margin: 0.35em 0;"><a href="#{anchor}" style="display: inline-block; padding: 0.35em 0.75em; border-radius: 6px; text-decoration: none; color: #0969da; font-size: 0.95em; background: #fff; border: 1px solid #d8dee4;">{keyword}</a></li>\n')
            f.write("  </ul>\n")
            f.write("</details>\n\n")

        for keyword in keys_to_show:
            day_content = data[keyword]
            if not day_content:
                continue
            # the head of each part
            f.write(f"## {keyword}\n\n")

            if use_title == True:
                if to_web == False:
                    if paper_tags:
                        f.write("|Publish Date|Title|Tag|Authors|PDF|\n" + "|---|---|---|---|---|\n")
                    else:
                        f.write("|Publish Date|Title|Authors|PDF|\n" + "|---|---|---|---|\n")
                else:
                    f.write("| Publish Date | Title | Authors | PDF |\n")
                    f.write("|:---------|:-----------------------|:---------|:------|\n")

            # sort papers by date
            day_content = sort_papers(day_content)

            for _, v in day_content.items():
                if v is not None:
                    if paper_tags:
                        title = extract_title_from_row(v)
                        tag = get_paper_tag(title, paper_tags)
                        row = format_row_with_tag(v, tag, PAPER_TAG_STYLES)
                        f.write(pretty_math(row))
                    else:
                        f.write(pretty_math(normalize_table_row(v)))

            f.write(f"\n")

            #Add: back to top
            if use_b2t:
                top_info = f"#Updated on {DateNow}"
                top_info = top_info.replace(' ','-').replace('.','')
                f.write(f"<p align=right>(<a href={top_info.lower()}>back to top</a>)</p>\n\n")

        if show_badge == True:
            # badge 使用 config 中的 user_name / repo_name，Fork 后只需改 config.yaml
            u, r = badge_user_name, badge_repo_name
            f.write((f"[contributors-shield]: https://img.shields.io/github/"
                     f"contributors/{u}/{r}.svg?style=for-the-badge\n"))
            f.write((f"[contributors-url]: https://github.com/{u}/{r}/graphs/contributors\n"))
            f.write((f"[forks-shield]: https://img.shields.io/github/forks/{u}/{r}.svg?style=for-the-badge\n"))
            f.write((f"[forks-url]: https://github.com/{u}/{r}/network/members\n"))
            f.write((f"[stars-shield]: https://img.shields.io/github/stars/{u}/{r}.svg?style=for-the-badge\n"))
            f.write((f"[stars-url]: https://github.com/{u}/{r}/stargazers\n"))
            f.write((f"[issues-shield]: https://img.shields.io/github/issues/{u}/{r}.svg?style=for-the-badge\n"))
            f.write((f"[issues-url]: https://github.com/{u}/{r}/issues\n\n"))

    logging.info(f"{task} finished")

def demo(**config):
    # TODO: use config
    data_collector = []
    data_collector_web= []

    keywords = config['kv']
    max_results = config['max_results']
    publish_readme = config['publish_readme']
    publish_gitpage = config['publish_gitpage']
    publish_wechat = config['publish_wechat']
    show_badge = config['show_badge']

    b_update = config['update_paper_links']
    logging.info(f'Update Paper Link = {b_update}')
    if config['update_paper_links'] == False:
        logging.info(f"GET daily papers begin")
        for topic, keyword in keywords.items():
            logging.info(f"Keyword: {topic}")
            data, data_web = get_daily_papers(topic, query = keyword,
                                            max_results = max_results)
            data_collector.append(data)
            data_collector_web.append(data_web)
            print("\n")
        logging.info(f"GET daily papers end")

        # 额外输出一份「本次抓取的增量论文」到 daily_new.md，方便按天查看新增
        try:
            write_daily_new_md("daily_new.md", data_collector, config)
            logging.info("Daily new papers written to daily_new.md")
        except Exception as e:
            logging.warning(f"Failed to write daily_new.md: {e}")

    # 1. update README.md file
    if publish_readme:
        json_file = config['json_readme_path']
        md_file   = config['md_readme_path']
        # update paper links
        if config['update_paper_links']:
            update_paper_links(json_file)
        else:
            # update json data
            update_json_file(json_file,data_collector)
        # json data to markdown
        json_to_md(json_file, md_file, task='Update Readme',
            show_badge=show_badge,
            badge_user_name=config.get('user_name', 'Vincentqyw'),
            badge_repo_name=config.get('repo_name', 'reco-arxiv-daily'),
            allowed_keywords=list(config['keywords'].keys()),
            paper_tags=config.get('paper_tags'))

    # 2. update docs/index.md file (to gitpage)
    if publish_gitpage:
        json_file = config['json_gitpage_path']
        md_file   = config['md_gitpage_path']
        # TODO: duplicated update paper links!!!
        if config['update_paper_links']:
            update_paper_links(json_file)
        else:
            update_json_file(json_file,data_collector)
        json_to_md(json_file, md_file, task='Update GitPage',
            to_web=True, show_badge=show_badge,
            use_tc=False, use_b2t=False,
            badge_user_name=config.get('user_name', 'Vincentqyw'),
            badge_repo_name=config.get('repo_name', 'reco-arxiv-daily'),
            allowed_keywords=list(config['keywords'].keys()))

    # 3. Update docs/wechat.md file
    if publish_wechat:
        json_file = config['json_wechat_path']
        md_file   = config['md_wechat_path']
        # TODO: duplicated update paper links!!!
        if config['update_paper_links']:
            update_paper_links(json_file)
        else:
            update_json_file(json_file, data_collector_web)
        json_to_md(json_file, md_file, task='Update Wechat',
            to_web=False, use_title=False, show_badge=show_badge,
            badge_user_name=config.get('user_name', 'Vincentqyw'),
            badge_repo_name=config.get('repo_name', 'reco-arxiv-daily'),
            allowed_keywords=list(config['keywords'].keys()))

    # 4. Generative / LLM / Scaling/Scale / Sequence/Sequential 四个 topic 合并输出一份 MD
    extra_md = config.get('extra_title_md', '').strip()
    extra_topics = config.get('extra_title_topics')
    if extra_md and extra_topics and config.get('publish_readme'):
        json_main = config['json_readme_path']
        json_extra_path = config.get('json_extra_title_path', './docs/reco-arxiv-daily-extra.json')
        try:
            with open(json_main, 'r') as f:
                data_main = json.load(f)
            filtered = {}
            topic_labels = []
            for item in extra_topics:
                label = item.get('label') or item.get('topic', '')
                words = item.get('words') or item.get('filters', [])
                if isinstance(words, str):
                    words = [words]
                if not label or not words:
                    continue
                topic_labels.append(label)
                papers = {}
                for source_topic in config['keywords'].keys():
                    if source_topic not in data_main or not data_main[source_topic]:
                        continue
                    for pid, row in data_main[source_topic].items():
                        if any(w.lower() in extract_title_from_row(row).lower() for w in words):
                            papers[pid] = row
                filtered[label] = papers
            if filtered and any(filtered.values()):
                os.makedirs(os.path.dirname(json_extra_path) or '.', exist_ok=True)
                with open(json_extra_path, 'w') as f:
                    json.dump(filtered, f)
                json_to_md(json_extra_path, extra_md, task='Update Extra Title MD',
                    show_badge=show_badge,
                    badge_user_name=config.get('user_name', 'Vincentqyw'),
                    badge_repo_name=config.get('repo_name', 'reco-arxiv-daily'),
                    allowed_keywords=topic_labels)
                logging.info(f'Extra title MD: {extra_md} (topics {topic_labels})')
        except Exception as e:
            logging.warning(f'Skip extra_title_md: {e}')

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config_path',type=str, default='config.yaml',
                            help='configuration file path')
    parser.add_argument('--update_paper_links', default=False,
                        action="store_true",help='whether to update paper links etc.')
    args = parser.parse_args()
    config = load_config(args.config_path)
    config = {**config, 'update_paper_links':args.update_paper_links}
    demo(**config)
