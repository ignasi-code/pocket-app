import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BUFFER_API_URL = "https://api.buffer.com"
VALID_POST_MODES = {"addToQueue", "shareNow", "shareNext", "customScheduled"}
VALID_SCHEDULING_TYPES = {"automatic", "notification"}
VALID_METADATA_SERVICES = {"instagram"}
VALID_INSTAGRAM_POST_TYPES = {"post", "story", "reel"}


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


def create_post(
    api_key,
    channel_id,
    text,
    image_url=None,
    image_width=None,
    image_height=None,
    image_alt_text=None,
    mode="addToQueue",
    scheduling_type="automatic",
    due_at=None,
    save_to_draft=False,
    metadata_service="instagram",
    post_type="post",
):
    channel_id = str(channel_id or "").strip()
    text = str(text or "").strip()
    image_url = str(image_url or "").strip()
    image_alt_text = str(image_alt_text or "Maison Flou image study").strip()
    mode = str(mode or "addToQueue").strip()
    scheduling_type = str(scheduling_type or "automatic").strip()
    due_at = str(due_at or "").strip()
    save_to_draft = bool(save_to_draft)
    metadata_service = str(metadata_service or "").strip()
    post_type = str(post_type or "post").strip()

    if not channel_id:
        raise BufferApiError("BUFFER_CHANNEL_ID or channel_id is required.")
    if not text:
        raise BufferApiError("Post text is required.")
    if mode not in VALID_POST_MODES:
        raise BufferApiError(f"Unsupported Buffer post mode: {mode}")
    if scheduling_type not in VALID_SCHEDULING_TYPES:
        raise BufferApiError(f"Unsupported Buffer scheduling type: {scheduling_type}")
    if mode == "customScheduled" and not due_at:
        raise BufferApiError("due_at is required when mode is customScheduled.")
    if metadata_service and metadata_service not in VALID_METADATA_SERVICES:
        raise BufferApiError(f"Unsupported Buffer metadata service: {metadata_service}")
    if metadata_service == "instagram" and post_type not in VALID_INSTAGRAM_POST_TYPES:
        raise BufferApiError(f"Unsupported Instagram post type: {post_type}")
    if (image_width is None) != (image_height is None):
        raise BufferApiError("image_width and image_height must be provided together.")

    image_dimensions = ""
    if image_width is not None and image_height is not None:
        try:
            image_width = int(image_width)
            image_height = int(image_height)
        except (TypeError, ValueError) as exc:
            raise BufferApiError("image_width and image_height must be integers.") from exc
        if image_width <= 0 or image_height <= 0:
            raise BufferApiError("image_width and image_height must be positive.")
        image_dimensions = f"""
            metadata: {{
              altText: {_gql_string(image_alt_text)}
              dimensions: {{ width: {image_width}, height: {image_height} }}
            }}
        """

    assets = ""
    if image_url:
        assets = f"""
          assets: [{{ image: {{ url: {_gql_string(image_url)} {image_dimensions} }} }}]
        """

    due_at_field = f"dueAt: {_gql_string(due_at)}" if due_at else ""
    draft_field = "saveToDraft: true" if save_to_draft else ""
    metadata_field = ""
    if metadata_service == "instagram":
        share_to_feed = "true" if post_type == "reel" else "false"
        metadata_field = f"""
        metadata: {{ instagram: {{ type: {post_type}, shouldShareToFeed: {share_to_feed} }} }}
        """

    query = f"""
    mutation CreatePost {{
      createPost(input: {{
        text: {_gql_string(text)}
        channelId: {_gql_string(channel_id)}
        schedulingType: {scheduling_type}
        mode: {mode}
        {due_at_field}
        {draft_field}
        {metadata_field}
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
    result = graphql_request(api_key, query).get("createPost")
    if isinstance(result, dict) and result.get("message") and not result.get("post"):
        raise BufferApiError(result["message"])
    return result
