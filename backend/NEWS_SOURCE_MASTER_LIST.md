# 🌍 Priority News Engine: Master Source List

This document serves as the "Emergency Backup" and "Primary Intelligence" list for the Priority News Engine. It contains the original sources that power secondary aggregators like Inshorts and Hacker News.

---

## 🏛️ Tier 1: The Global Agencies (The "Raw" Data)
*These sources are where almost all news begins. They have reporters on the ground globally.*
- **Reuters**: [RSS Hub](https://reuters.com/tools/rss)
- **Associated Press (AP)**: [Top Stories](https://apnews.com/hub/ap-top-news)
- **Agence France-Presse (AFP)**: [Live Feed](https://www.afp.com/en/news-hub)

---

## 🇮🇳 Tier 2: Premium Indian Outlets (Primary for Inshorts)
*These sources provide the bulk of the National and Business news for the Indian market.*
- **The Hindu**: [International News](https://www.thehindu.com/news/international/feeder/default.rss)
- **The Economic Times**: [Business/Finance](https://economictimes.indiatimes.com/rss.cms)
- **LiveMint**: [Startups & Tech](https://www.livemint.com/rss/companies)
- **NDTV News**: [National Headlines](https://www.ndtv.com/rss)
- **MoneyControl**: [Markets & Stocks](https://www.moneycontrol.com/rss/latestnews.xml)

---

## 💻 Tier 3: Tech & Innovation (Primary for Hacker News)
*The most influential sites for Technology, AI, and Science.*
- **TechCrunch**: [Startups](https://techcrunch.com/feed/)
- **The Verge**: [Gadgets & Culture](https://www.theverge.com/rss/index.xml)
- **Wired**: [Innovation & Science](https://www.wired.com/feed/rss)
- **Ars Technica**: [Deep Tech Analysis](https://feeds.arstechnica.com/arstechnica/index)
- **Hacker News (Algolia Search)**: [HN Search API](https://hn.algolia.com/api)

---

## 📺 Tier 4: Broad International (Top Story Backups)
- **BBC News**: [World Service](http://feeds.bbci.co.uk/news/world/rss.xml)
- **The New York Times**: [World Feed](https://rss.nytimes.com/services/xml/rss/nyt/World.xml)
- **Al Jazeera**: [Global Perspective](https://www.aljazeera.com/xml/rss/all.xml)

---

## 🛠️ Implementation Continuity Note
If either `inshortsrss` or `hnrss` (our current bridges) are deactivated or blocked, the developer should migrate the `fetchers.py` logic to crawl the **Tier 1** and **Tier 2** RSS feeds listed above directly.

---
*Created on April 10, 2026 - Documenting the foundation of the News Engine.*
