# Troubleshooting Guide

## Error Codes

| Code | Meaning | Fix |
|------|---------|-----|
| PIPELINE_TIMEOUT | Pipeline exceeded timeout | Increase SCOPE_GENERATE_TIMEOUT or check API connectivity |
| DATA_FETCH_FAILED | MongoDB API unreachable | Check API_BASE_URL and API_AUTH_TOKEN in .env |
| LLM_ERROR | OpenAI API error | Check OPENAI_API_KEY, model availability, rate limits |
| DOCUMENT_GENERATION_FAILED | Doc generation failed | Check disk space, python-docx/reportlab installed |

## Common Issues

### API unreachable
- Verify: `curl http://localhost:8003/health`
- Check: `systemctl status construction-agent`
- Logs: `journalctl -u construction-agent -f`

### Documents not downloading
- Verify S3: check STORAGE_BACKEND in .env (should be "s3")
- Check AWS credentials in .env
- Test: `python -c "from s3_utils.client import get_s3_client; print(get_s3_client())"`

### Pipeline slow
- Check PARALLEL_FETCH_CONCURRENCY (default 30)
- Check NOTE_MAX_CHARS for compression level
- Monitor via /api/scope-gap/metrics
