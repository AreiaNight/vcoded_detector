# 𝐕𝐢𝐛𝐞 𝐜𝐨𝐝𝐞𝐝 𝐝𝐞𝐭𝐞𝐜𝐭𝐨𝐫

> A simply vibe code detector

**vcoded_detector** is a tool that analyzes websites for patterns and keywords associated with vibe-coded (AI-generated) code. Paste the link of any page: the tool downloads its source code, checks it against a list of patterns (`wordlist.txt`), and displays statistics in a web dashboard.

![Dashboard preview](docs/dashboard.png)

## 𝐅𝐞𝐚𝐭𝐮𝐫𝐞𝐬

 <img src="https://i.pinimg.com/736x/b1/28/89/b12889ec1860d4b8223491db1ceaa8fa.jpg" alt="img" align="right" width="400px"> <br><br>
<br><br><br>

- Analyzes the source code of any public URL.
- Detects patterns and keywords defined in an editable wordlist.
- Simple web dashboard: just paste the link.
- Match statistics once the analysis finishes.

## 𝐇𝐨𝐰 𝐈𝐭 𝐖𝐨𝐫𝐤𝐬

1. You enter a URL in the dashboard.
2. `crawler.py` fetches the page's source code.
3. The source is checked against the entries in `wordlist.txt`.
4. The dashboard displays the analysis statistics.

## 𝐏𝐫𝐨𝐣𝐞𝐜𝐭 𝐒𝐭𝐫𝐮𝐜𝐭𝐮𝐫𝐞

| File | Description |
|---|---|
| `crawler.py` | Downloads the URL's source code and runs detection. |
| `dashboard.go` | Web server that serves the dashboard. |
| `Dashboard.html` | Main interface. |
| `script.js` | Frontend logic. |
| `styles.css` | Dashboard styles. |
| `wordlist.txt` | List of patterns and keywords to search for. |

## 𝐑𝐞𝐪𝐮𝐢𝐫𝐞𝐦𝐞𝐧𝐭𝐬

- Python 3.[VERSION] or later
- Go [VERSION] or later
- [Python dependencies, if any, listed in `requirements.txt`]

## 𝐈𝐧𝐬𝐭𝐚𝐥𝐥𝐚𝐭𝐢𝐨𝐧

```bash
git clone https://github.com/AreiaNight/vcoded_detector.git
cd vcoded_detector
```

## 𝐔𝐬𝐚𝐠𝐞

### 𝐑𝐮𝐧𝐧𝐢𝐧𝐠 𝐋𝐨𝐜𝐚𝐥𝐥𝐲

Start the dashboard server:

```bash
go run dashboard.go
```

Open in your browser:

```
http://localhost:8080
```

Paste the link of the page you want to analyze and review the stats.

![Dashboard preview](docs/stats.png)

### 𝐂𝐮𝐬𝐭𝐨𝐦𝐢𝐳𝐢𝐧𝐠 𝐭𝐡𝐞 𝐖𝐨𝐫𝐝𝐥𝐢𝐬𝐭

Edit `wordlist.txt` to add or remove patterns, or change the path to the list directly in `crawler.py` or `dashboard.go`.

## 𝐒𝐞𝐫𝐯𝐞𝐫 𝐃𝐞𝐩𝐥𝐨𝐲𝐦𝐞𝐧𝐭

The recommended approach is to run the tool on a server so it stays available.

### 𝟏. 𝐏𝐫𝐞𝐩𝐚𝐫𝐞 𝐭𝐡𝐞 𝐒𝐞𝐫𝐯𝐞𝐫

A Linux server (Ubuntu 22.04 or similar) with SSH access, and Go and Python 3 installed.

### 𝟐. 𝐂𝐥𝐨𝐧𝐞 𝐚𝐧𝐝 𝐁𝐮𝐢𝐥𝐝

```bash
git clone https://github.com/AreiaNight/vcoded_detector.git
cd vcoded_detector
go build -o vcoded_detector dashboard.go
```

### 𝟑. 𝐑𝐮𝐧 𝐚𝐬 𝐚 𝐒𝐞𝐫𝐯𝐢𝐜𝐞 (𝐬𝐲𝐬𝐭𝐞𝐦𝐝)

Create the file `/etc/systemd/system/vcoded_detector.service`:

```ini
[Unit]
Description=vcoded_detector dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/vcoded_detector
ExecStart=/opt/vcoded_detector/vcoded_detector
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

Then enable the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vcoded_detector
sudo systemctl status vcoded_detector
```

### 𝟒. (𝐎𝐩𝐭𝐢𝐨𝐧𝐚𝐥) 𝐑𝐞𝐯𝐞𝐫𝐬𝐞 𝐏𝐫𝐨𝐱𝐲 𝐰𝐢𝐭𝐡 𝐍𝐠𝐢𝐧𝐱 𝐚𝐧𝐝 𝐇𝐓𝐓𝐏𝐒

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:[PORT];
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

For HTTPS, you can use Certbot:

```bash
sudo certbot --nginx -d your-domain.com
```
