import os
import datetime
from fastmcp import FastMCP
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

mcp = FastMCP("Google Calendar")

def get_calendar_service():
    """Authenticate and return the Google Calendar service."""
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("credentials.json"):
                raise Exception(
                    "credentials.json not found! "
                    "Please download OAuth 2.0 Client credentials from Google Cloud Console "
                    "and save them as 'credentials.json' in this directory."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            # This prints a link for the user to authenticate manually, avoiding the headless browser error
            creds = flow.run_local_server(port=0, open_browser=False)
            
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)

@mcp.tool()
def get_upcoming_events(max_results: int = 10) -> str:
    """
    Get the user's upcoming Google Calendar events.
    
    Args:
        max_results: The maximum number of events to return.
    """
    try:
        service = get_calendar_service()
        now = datetime.datetime.utcnow().isoformat() + "Z"  # 'Z' indicates UTC time
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        if not events:
            return "No upcoming events found."

        result = "Upcoming events:\n"
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            result += f"- {start}: {event['summary']}\n"
        return result
    except Exception as e:
        return f"Error fetching events: {str(e)}"

@mcp.tool()
def book_meeting(title: str, start_time: str, end_time: str, attendees: list[str] = None) -> str:
    """
    Book a meeting on the user's Google Calendar.
    
    Args:
        title: The title or summary of the meeting.
        start_time: Start time in ISO format (e.g., '2026-06-08T09:00:00-07:00').
        end_time: End time in ISO format (e.g., '2026-06-08T10:00:00-07:00').
        attendees: Optional list of email addresses to invite.
    """
    try:
        service = get_calendar_service()
        
        event = {
            'summary': title,
            'start': {
                'dateTime': start_time,
            },
            'end': {
                'dateTime': end_time,
            },
        }
        
        if attendees:
            event['attendees'] = [{'email': email} for email in attendees]

        event = service.events().insert(calendarId='primary', body=event).execute()
        return f"Event created successfully! Link: {event.get('htmlLink')}"
    except Exception as e:
        return f"Error booking meeting: {str(e)}"

if __name__ == "__main__":
    # Authenticate on startup so the user can log in immediately
    print("Initializing Google Calendar connection...")
    get_calendar_service()
    
    # Start the MCP streamable-http server so Dograh can connect to it
    print("Starting Google Calendar MCP server on port 8080...")
    mcp.run(transport="streamable-http", port=8080, host="0.0.0.0")
