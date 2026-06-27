from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from slack_app.handlers.oauth import build_install_url, handle_oauth_callback

router = APIRouter(prefix="/slack", tags=["slack-oauth"])


@router.get("/install")
def install():
    """The 'Add to Slack' button on your landing page points here."""
    return RedirectResponse(url=build_install_url())


@router.get("/oauth/callback")
def oauth_callback(code: str = None, error: str = None):
    """
    Slack redirects here after the company approves install.
    This is the SLACK_REDIRECT_URI you configure in your Slack app settings
    and pass to oauth.v2.access.
    """
    if error:
        raise HTTPException(status_code=400, detail=f"Slack OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code parameter")

    try:
        workspace = handle_oauth_callback(code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "message": "Delegate installed successfully",
        "team_name": workspace["team_name"],
    }