# 🏛️ WA Legislative Tracker 2026 - GitHub Pages Edition

A free, open-source bill tracking system for the Washington State Legislature 2026 session. Deployed entirely on GitHub Pages with automatic daily updates via GitHub Actions.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Updates](https://img.shields.io/badge/updates-daily-green.svg)
![Session](https://img.shields.io/badge/session-2026-purple.svg)

## 🌟 Features

- **No Backend Required**: Runs entirely on GitHub Pages (free hosting)
- **Automatic Updates**: GitHub Actions fetches new bills daily
- **Personal Tracking**: Track bills of interest with browser storage
- **Modern UI**: Dark theme with responsive design
- **Privacy First**: All personal data stays in your browser
- **Zero Cost**: Completely free to deploy and maintain

## 🚀 Quick Deploy Guide

### Step 1: Fork or Create Repository

1. **Create a new GitHub repository** named `wa-bill-tracker`
2. Make sure to **check** "Add a README file" when creating

### Step 2: Enable GitHub Pages

1. Go to **Settings** → **Pages** in your repository
2. Under "Source", select **Deploy from a branch**
3. Choose **main** branch and **/ (root)** folder
4. Click **Save**

### Step 3: Upload Files

1. Upload these files to your repository:
   - `index.html` (main application)
   - `.github/workflows/update-data.yml` (automation)
   - `scripts/fetch_bills.py` (data fetcher)

### Step 4: Create Data Repository (Optional but Recommended)

For automatic updates, create a separate data repository:

1. Create a new repository named `wa-bill-tracker-data`
2. Create a `data` folder
3. Add an empty `bills.json` file

### Step 5: Configure the Application

Edit `index.html` and update line ~650:
```javascript
const GITHUB_CONFIG = {
    owner: 'YOUR_GITHUB_USERNAME', // Change this
    repo: 'wa-bill-tracker-data',  // Your data repo name
    branch: 'main',
    dataPath: 'data/bills.json',
    syncPath: 'data/sync-log.json'
};
```

## 🔒 Making Repository Private with Public Website

GitHub Pages from private repositories is a **Pro/Team** feature. However, you have options:

### Option A: Public Repository (Free)
- Repository is public
- Website is public at `https://USERNAME.github.io/wa-bill-tracker`
- Code is visible to everyone

### Option B: Private Repository (Requires GitHub Pro)
1. **Upgrade to GitHub Pro** ($4/month for individuals)
2. Make repository private: **Settings** → **General** → **Danger Zone** → **Change visibility**
3. Enable GitHub Pages from private repo
4. Website remains publicly accessible
5. Code stays private

### Option C: Hybrid Approach (Free)
1. Keep main repository public for the website
2. Create a separate private repository for sensitive scripts
3. Use GitHub Actions to sync between them

### Option D: Separate Data Repository
1. Main app repository: **Public** (for GitHub Pages)
2. Data repository: **Private** (if you have Pro) or **Public**
3. App fetches data from data repository via GitHub API

## 🔧 Configuration

### Automatic Updates

The GitHub Action runs daily at 2 AM PST. To modify:

Edit `.github/workflows/update-data.yml`:
```yaml
schedule:
  - cron: '0 10 * * *'  # Change this (UTC time)
```

### Manual Updates

1. Go to **Actions** tab in your repository
2. Select "Update Legislative Data"
3. Click "Run workflow"

## 💾 Local Development

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/wa-bill-tracker.git
cd wa-bill-tracker

# Open in browser
open index.html

# Or use a local server
python -m http.server 8000
# Visit http://localhost:8000
```

## 🎨 Customization

### Change Color Theme

Edit the CSS variables in `index.html`:
```css
:root {
    --primary: #0f172a;    /* Main background */
    --accent: #3b82f6;     /* Primary accent color */
    --success: #10b981;    /* Success indicators */
    --warning: #f59e0b;    /* Warning indicators */
}
```

## 📊 Data Structure

Bills are stored in JSON format:
```json
{
  "lastSync": "2026-01-12T10:00:00Z",
  "bills": [{
    "id": "HB1234",
    "number": "HB 1234",
    "title": "Bill Title",
    "sponsor": "Rep. Name",
    "status": "prefiled|introduced|committee|passed|failed",
    "priority": "high|medium|low"
  }]
}
```

## 🛠️ Troubleshooting

### GitHub Pages not working?
- Check Settings → Pages is enabled
- Wait 5-10 minutes for initial deployment
- Check Actions tab for deployment status

### Data not updating?
- Check Actions tab for workflow runs
- Verify GITHUB_CONFIG settings in index.html
- Try clearing browser cache

## 📜 License

MIT License - Free to use and modify

## 🔗 Links

- [Live Demo](https://USERNAME.github.io/wa-bill-tracker)
- [WA Legislature Official Site](https://app.leg.wa.gov/)
- [GitHub Pages Documentation](https://docs.github.com/pages)

---

Built with ❤️ for Washington State civic engagement