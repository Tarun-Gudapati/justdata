from dotenv import load_dotenv
import anthropic

load_dotenv()
client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=1000,
    messages=[
        {"role": "user", "content": "why ironman is the best avenger?"}
    ]
)
print(response.content[0].text)
print(response.usage.total_tokens)