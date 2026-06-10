# Google Calendar MCP Server

This is a standalone Model Context Protocol (MCP) server for Google Calendar, designed to integrate seamlessly with Dograh.

## Setup Instructions

1. **Get Google OAuth Credentials:**
   - Go to the [Google Cloud Console](https://console.cloud.google.com/).
   - Create a new project or select an existing one.
   - Go to **APIs & Services > Library** and enable the **Google Calendar API**.
   - Go to **APIs & Services > Credentials** and click **Create Credentials > OAuth client ID**.
   - Choose **Desktop app** as the application type.
   - Click **Download JSON** and save the file in this directory as exactly `credentials.json`.

2. **Install Dependencies:**
   Ensure your Python virtual environment is activated, then run:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the Server:**
   ```bash
   python server.py
   ```
   *Note: On your very first run, it will open a browser window asking you to log into your Google Account to authorize calendar access. Once you accept, a `token.json` file will be generated locally and it will start the SSE server on port 8080.*

## Connecting to Dograh

1. Open your Dograh UI and go to **Tools**.
2. Click **Create Tool** and choose the **MCP** category.
3. Configure the MCP settings:
   - **Protocol**: `HTTP SSE`
   - **URL**: `http://localhost:8080/sse` (or `http://host.docker.internal:8080/sse` if running Dograh in Docker but the server on your host machine)
4. Save the tool! The Dograh agents can now check availability and book meetings on your Google Calendar.
