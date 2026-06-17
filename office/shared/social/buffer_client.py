import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BUFFER_API_URL = "https://api.buffer.com"
VALID_POST_MODES = {"addToQueue", "shareNow", "shareNext"}
VALID_SCHEDULING_TYPES = {"automatic", "notification"}


class BufferApiError(RuntimeError):
    pass


def _gql_string(value):
    return json.dumps(str(value or ""))


def _read_error(exc):
    try:
        return exc.read().decode("utf-8", "replace")
    except Exception:
        return str(exc)


def graphql_request(api_key, query, timeout=30):
    api_key = str(api_key or "").strip()
    if not api_key:
        raise BufferApiError("BUFFER_API_KEY is not configured.")

    payload = json.dumps({"query": query}).encode("utf-8")
    request = Request(
        BUFFER_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "pocket-office-buffer/0.1",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raise BufferApiError(f"Buffer HTTP {exc.code}: {_read_error(exc)}") from exc
    except URLError as exc:
        raise BufferApiError(f"Buffer network error: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BufferApiError(f"Buffer returned invalid JSON: {raw[:500]}") from exc

    if data.get("errors"):
        raise BufferApiError(json.dumps(data["errors"], ensure_ascii=True))
    return data.get("data", data)


def get_account(api_key):
    query = """
    query GetAccount {
      account {
        id
        email
        name
        organizations {
          id
          name
          ownerEmail
        }
      }
    }
    """
    return graphql_request(api_key, query).get("account")


def get_organizations(api_key):
    account = get_account(api_key) or {}
    return account.get("organizations") or []


def get_channels(api_key, organization_id):
    if not str(organization_id or "").strip():
        raise BufferApiError("BUFFER_ORGANIZATION_ID is required to list channels.")
    query = f"""
    query GetChannels {{
      channels(input: {{ organizationId: {_gql_string(organization_id)} }}) {{
        id
        name
        displayName
        service
        avatar
        isQueuePaused
      }}
    }}
    """
    return graphql_request(api_key, query).get("channels") or []


def create_post(api_key, channel_id, text, image_url=None, mode="addToQueue", scheduling_type="automatic"):
    channel_id = str(channel_id or "").strip()
    text = str(text or "").strip()
    image_url = str(image_url or "").strip()
    mode = str(mode or "addToQueue").strip()
    scheduling_type = str(scheduling_type or "automatic").strip()

    if not channel_id:
        raise BufferApiError("BUFFER_CHANNEL_ID or channel_id is required.")
    if not text:
        raise BufferApiError("Post text is required.")
    if mode not in VALID_POST_MODES:
        raise BufferApiError(f"Unsupported Buffer post mode: {mode}")
    if scheduling_type not in VALID_SCHEDULING_TYPES:
        raise BufferApiError(f"Unsupported Buffer scheduling type: {scheduling_type}")

    assets = ""
    if image_url:
        assets = f"""
          assets: [{{ image: {{ url: {_gql_string(image_url)} }} }}]
        """

    query = f"""
    mutation CreatePost {{
      createPost(input: {{
        text: {_gql_string(text)}
        channelId: {_gql_string(channel_id)}
        schedulingType: {scheduling_type}
        mode: {mode}
        {assets}
      }}) {{
        ... on PostActionSuccess {{
          post {{
            id
            text
            assets {{
              id
              mimeType
            }}
          }}
        }}
        ... on MutationError {{
          message
        }}
      }}
    }}
    """
    return graphql_request(api_key, query).get("createPost")
