import json
from api.services.configuration.registry import OpenAITTSService
print("MODEL SCHEMA:")
print(json.dumps(OpenAITTSService.model_json_schema()['properties']['model'], indent=2))
print("VOICE SCHEMA:")
print(json.dumps(OpenAITTSService.model_json_schema()['properties']['voice'], indent=2))
