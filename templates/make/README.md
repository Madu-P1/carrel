# Make Workflow Notes

Recommended scenario order:

1. Webhook or Google Drive trigger
2. Parse file content
3. `chunk-content.json` HTTP request
4. `generate-quiz.json` HTTP request
5. Notion create item or iterator over generated questions
6. Optional Slack notification

Replace:

- `sk-ant-YOURAPIKEY`
- `{{file_content}}`
- `{{concepts_from_previous_step}}`

The local app in `/Users/madu/Desktop/Codex/index.html` uses a mock upload flow; swap that for a Make webhook when you are ready.
