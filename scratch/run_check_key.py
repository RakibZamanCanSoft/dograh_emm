import asyncio
import sys
sys.path.insert(0, "/workspaces/dograh")

from api.db import db_client
from api.services.workflow.prompt_refactor import refactor_workflow_prompts

SAMPLE_CALL_PROMPT = """# MAIN ACTION POINT AT THIS STEP:
## Usable details and Main Agenda

<FORMAT>
## USABLE DETAILS and GOALS AT THIS STAGE:
1. **Collect Basic Information:**
   - Gather the caller's first and last name for record purposes.
   - Obtain the caller's contact information, including phone number and email address, to ensure follow-up communication if necessary.

2. **Child's Information:**
   - Capture the child's first and last name to personalize the service.
   - Record the child's age to tailor the therapy approach appropriately.
   - Understand the child's specific issue or concern.

3. **Appointment Scheduling Preferences:**
   - Ask for the preferred date and time for the appointment to check availability and facilitate scheduling.

[[ Relevant Questions: ]]
- May I have your first and last name, please?
- Could you provide your email address?
- Could you provide your phone number?
- What is your child's first and last name?
- How old is your child?
- Could you describe the issue or concern your child is facing?
- What date and time would you prefer for the appointment?

[[ Brief Wrap Up Details: ]]
- Confirm the collected information: repeat the caller's name, contact details, child's name and age, the issue described, and the preferred appointment date and time.
- Assure them that their details have been successfully added to the appointment waitlist.
- Thank the caller for providing the information and reassure them that someone from Meadow Mind Speech Therapy will be in touch soon regarding the appointment. 
</FORMAT>

## Flow of call
This node owns the full working part of the conversation.
Start by acknowledging what you understood from the opening stage.
Then ask focused questions one by one, resolve the issue if possible, and guide the caller through practical next steps.

Stay in this node until the issue is handled.
There is no separate summary node.

## Constraints
- Do not ask the same question again if the caller already answered it.
- Do not promise an email, callback, ticket number, or any follow up unless that capability is explicitly available.
- Never mix text and tool calls in the same output."""

SAMPLE_END_PROMPT = """# Main Action Point for This Stage

At this stage, the conversation with the user is complete. They have no further questions. Your job is to end the call politely and immediately. Do **not** start any new topics. Even if there are unresolved threads, you must ignore them and proceed to close the conversation. Do **not** wait for the user, do **not** ask questions, and do **not** hand the turn back to them.


**Generate a brief response (6–8 words)** that naturally follows from the user’s last message. Example: "Thank you for the call. And have - a wonderful day"

After this, say nothing else. The call is over."""

async def check():
    org_id = 1
    key = await db_client.get_configuration_value(organization_id=org_id, key="prompt_refactor_openai_api_key")
    print(f"Stored key for org {org_id}: {key[:8] if key else None}...")
    
    workflow_def = {
        "nodes": [
            {
                "type": "agentNode",
                "data": {
                    "prompt": SAMPLE_CALL_PROMPT
                }
            },
            {
                "type": "endCall",
                "data": {
                    "prompt": SAMPLE_END_PROMPT
                }
            }
        ]
    }
    
    await refactor_workflow_prompts(workflow_def, "call_and_chat", organization_id=org_id)
    
    agent_node = workflow_def["nodes"][0]["data"]
    end_node = workflow_def["nodes"][1]["data"]
    
    print("\n=================== AGENT NODE CALL PROMPT ===================")
    print(agent_node.get("prompt"))
    print("\n=================== AGENT NODE CHAT PROMPT ===================")
    print(agent_node.get("prompt_chat"))
    print("\n=================== END NODE CALL PROMPT ===================")
    print(end_node.get("prompt"))
    print("\n=================== END NODE CHAT PROMPT ===================")
    print(end_node.get("prompt_chat"))

if __name__ == "__main__":
    asyncio.run(check())
