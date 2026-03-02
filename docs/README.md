<p align="center">
  <h1 align="center"><br><ins>RECO-ARXIV-DAILY</ins><br>Automatically Update Recommendation ArXiv Papers Daily using Github Actions</h1>
 
</p>



##

This repository hosts the source code for reco-arxiv-daily, scripts to fetch recommendation-related arxiv papers daily. 

## Overview

This codebase is composed of the following parts:

- `daily_arxiv.py`: main scripts to processing given configurations
- `config.yaml`: configuration file of papers' keywords etc.

## Usage

<details>
  <summary>Table of Contents</summary>

1. Fork this [repo](https://github.com/ShawnBIT/reco-arxiv-daily)
2. Edit configs:
    - Change `GITHUB_USER_NAME` and `GITHUB_USER_EMAIL` in [cv-arxiv-daily.yml](../.github/workflows/cv-arxiv-daily.yml) and [update_paper_links.yml](../.github/workflows/update_paper_links.yml)
    - Change `user_name` and `repo_name` in [config.yaml](../config.yaml)
    - Push changes to remote repo
3. Config Github Actions
    - Enable read and write permissions: Setting -> Actions -> Workflow permissions, select `Read and write permissions` and save.
    - Enable workflows: Actions -> enable workflows -> Select `Run Arxiv Papers Daily` and `Run Update Paper Links Weekly`, then run workflow manually to test.
    - **自动每日更新**：`Run Arxiv Papers Daily` 已配置为每天 00:00 UTC 定时执行（可在 `.github/workflows/cv-arxiv-daily.yml` 的 `schedule` 里改 cron），执行时会拉取新论文、更新 README 并自动 commit 推送。
4. Setting Gitpages (optional)
    - Setting -> Pages -> Build and deployment. Source: `Deploy from a branch`; Branch select `main` and `/docs` folder, then save.
    - Now you can open gitpage: https://ShawnBIT.github.io/reco-arxiv-daily
5. Add new keywords (optional)
    - Edit `keywords` in [config.yaml](../config.yaml), you can add more filters or keywords.
    - Push changes to remote repo and re-run Github Actions Manually.

</details>

## Release plan

 We are still in the process of fully releasing. Here is the release plan:

- [x] Configuration file
- [x] Update code link
- [ ] Subscribe & Update alerting
- [ ] Support more `arxiv` filters
- [ ] Archive old papers
- [ ] Language translation ([`ChatGPT`](https://chat.openai.com/chat))
- [ ] Usefull comments
- [ ] ...
