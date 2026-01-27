"""
DhanHQ Authentication Module (v2.2.0).

This module provides OAuth and TOTP authentication using DhanLogin.
Simply run: python auth.py

Usage:
    # OAuth Flow (opens browser)
    python auth.py

    # PIN + TOTP Flow (programmatic)
    python auth.py --totp

    # In your code
    from auth import get_access_token, get_dhan_context
    context = get_dhan_context()  # Returns DhanContext for API calls
"""

import json
import os
import sys
import webbrowser
from dataclasses import dataclass
from pathlib import Path

try:
    from dhanhq import DhanContext, DhanLogin
except ImportError:
    print("Error: dhanhq>=2.2.0 not installed. Run: pip install dhanhq>=2.2.0")
    sys.exit(1)

# Token file location (in project root)
TOKEN_FILE = Path(__file__).parent / ".dhan_token.json"


@dataclass
class DhanCredentials:
    """Stored Dhan credentials and tokens."""

    client_id: str
    access_token: str
    app_id: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return {
            "client_id": self.client_id,
            "access_token": self.access_token,
            "app_id": self.app_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DhanCredentials":
        """Create from dictionary."""
        return cls(
            client_id=data["client_id"],
            access_token=data["access_token"],
            app_id=data.get("app_id", ""),
        )


def save_credentials(credentials: DhanCredentials) -> None:
    """Save credentials to token file."""
    with open(TOKEN_FILE, "w") as f:
        json.dump(credentials.to_dict(), f, indent=2)
    print(f"\n[OK] Token saved to {TOKEN_FILE}")


def load_credentials() -> DhanCredentials | None:
    """Load credentials from token file if exists."""
    if not TOKEN_FILE.exists():
        return None
    try:
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
        return DhanCredentials.from_dict(data)
    except (json.JSONDecodeError, KeyError):
        return None


def get_access_token() -> str:
    """
    Get access token from saved credentials or environment variable.

    Returns:
        Access token string

    Raises:
        ValueError: If no token is available
    """
    credentials = load_credentials()
    if credentials:
        return credentials.access_token

    env_token = os.getenv("DHAN_ACCESS_TOKEN")
    if env_token and env_token != "YOUR_ACCESS_TOKEN":
        return env_token

    raise ValueError(
        "No access token found. Run 'python auth.py' to authenticate, "
        "or set DHAN_ACCESS_TOKEN environment variable."
    )


def get_client_id() -> str:
    """
    Get client ID from saved credentials or environment variable.

    Returns:
        Client ID string

    Raises:
        ValueError: If no client ID is available
    """
    credentials = load_credentials()
    if credentials:
        return credentials.client_id

    env_client_id = os.getenv("DHAN_CLIENT_ID")
    if env_client_id and env_client_id != "YOUR_CLIENT_ID":
        return env_client_id

    raise ValueError(
        "No client ID found. Run 'python auth.py' to authenticate, "
        "or set DHAN_CLIENT_ID environment variable."
    )


def get_dhan_context() -> DhanContext:
    """
    Get DhanContext for API initialization.

    Returns:
        DhanContext object for use with dhanhq, MarketFeed, OrderUpdate

    Raises:
        ValueError: If credentials not available
    """
    return DhanContext(get_client_id(), get_access_token())


def oauth_login() -> DhanCredentials:
    """
    Perform OAuth browser-based login using DhanLogin.

    Returns:
        DhanCredentials with access token
    """
    print("=" * 60)
    print("DhanHQ OAuth Authentication")
    print("=" * 60)
    print()
    print("Enter your Dhan API credentials (from https://developers.dhan.co/):")
    print()

    client_id = input("Client ID: ").strip()
    if not client_id:
        print("Error: Client ID is required")
        sys.exit(1)

    app_id = input("App ID: ").strip()
    if not app_id:
        print("Error: App ID is required")
        sys.exit(1)

    app_secret = input("App Secret: ").strip()
    if not app_secret:
        print("Error: App Secret is required")
        sys.exit(1)

    print()
    print("-" * 60)
    print("Starting OAuth flow...")
    print()

    # Initialize DhanLogin
    dhan_login = DhanLogin(client_id)

    # Step 1: Generate consent
    print("Step 1: Generating login session...")
    try:
        consent_id = dhan_login.generate_login_session(app_id, app_secret)
        print(f"[OK] Consent ID generated: {consent_id}")
    except Exception as e:
        print(f"Error generating login session: {e}")
        sys.exit(1)

    print()
    print("A browser window will open for you to login to Dhan.")
    input("Press Enter to open the browser...")

    # Open browser for login
    login_url = f"https://login.dhan.co/?consent_id={consent_id}"
    webbrowser.open(login_url)

    print()
    print("-" * 60)
    print("After logging in, copy the 'token_id' from the redirect URL.")
    print("The URL will look like: https://yourapp.com/?token_id=XXXXX")
    print("-" * 60)
    print()

    # Step 2: Get token ID from user
    token_id = input("Enter the Token ID from the redirect URL: ").strip()
    if not token_id:
        print("Error: Token ID is required")
        sys.exit(1)

    # Step 3: Exchange token ID for access token
    print()
    print("Step 2: Exchanging Token ID for Access Token...")
    try:
        access_token = dhan_login.consume_token_id(token_id, app_id, app_secret)
        print("[OK] Access token obtained successfully!")
    except Exception as e:
        print(f"Error obtaining access token: {e}")
        sys.exit(1)

    # Validate token with user profile
    print()
    print("Step 3: Validating token...")
    try:
        user_info = dhan_login.user_profile(access_token)
        print(f"[OK] Logged in as: {user_info.get('name', 'Unknown')}")
    except Exception as e:
        print(f"Warning: Could not validate profile: {e}")

    # Create and save credentials
    credentials = DhanCredentials(
        client_id=client_id,
        access_token=access_token,
        app_id=app_id,
    )
    save_credentials(credentials)

    print()
    print("=" * 60)
    print("[OK] Authentication successful!")
    print("=" * 60)
    print()
    print("You can now run the trading bot with: python main.py")
    print()

    return credentials


def totp_login() -> DhanCredentials:
    """
    Perform PIN + TOTP programmatic login using DhanLogin.

    Returns:
        DhanCredentials with access token
    """
    print("=" * 60)
    print("DhanHQ PIN + TOTP Authentication")
    print("=" * 60)
    print()

    client_id = input("Client ID: ").strip()
    if not client_id:
        print("Error: Client ID is required")
        sys.exit(1)

    pin = input("PIN: ").strip()
    if not pin:
        print("Error: PIN is required")
        sys.exit(1)

    totp = input("TOTP (from authenticator app): ").strip()
    if not totp:
        print("Error: TOTP is required")
        sys.exit(1)

    print()
    print("Generating access token...")

    # Initialize DhanLogin and generate token
    dhan_login = DhanLogin(client_id)

    try:
        token_data = dhan_login.generate_token(pin, totp)
        access_token = token_data.get("access_token", token_data)
        if isinstance(access_token, dict):
            access_token = access_token.get("accessToken", str(token_data))
        print("[OK] Access token generated!")
    except Exception as e:
        print(f"Error generating token: {e}")
        sys.exit(1)

    # Create and save credentials
    credentials = DhanCredentials(
        client_id=client_id,
        access_token=str(access_token),
    )
    save_credentials(credentials)

    print()
    print("=" * 60)
    print("[OK] Authentication successful!")
    print("=" * 60)
    print()

    return credentials


def renew_token() -> None:
    """Renew existing access token."""
    credentials = load_credentials()
    if not credentials:
        print("No saved credentials. Run 'python auth.py' first.")
        sys.exit(1)

    print("Renewing access token...")

    dhan_login = DhanLogin(credentials.client_id)
    try:
        dhan_login.renew_token(credentials.access_token)
        print("[OK] Token renewed successfully!")
    except Exception as e:
        print(f"Error renewing token: {e}")
        print("You may need to re-authenticate with 'python auth.py'")
        sys.exit(1)


def clear_credentials() -> None:
    """Remove saved credentials."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        print(f"[OK] Removed {TOKEN_FILE}")
    else:
        print("No saved credentials found.")


def show_status() -> None:
    """Show current authentication status."""
    print("=" * 60)
    print("DhanHQ Authentication Status")
    print("=" * 60)
    print()

    credentials = load_credentials()
    if credentials:
        print("[OK] Authenticated (saved token)")
        print(f"  Client ID: {credentials.client_id}")
        print(f"  Token: {credentials.access_token[:20]}...")
        print(f"  Token file: {TOKEN_FILE}")

        # Try to validate profile
        try:
            dhan_login = DhanLogin(credentials.client_id)
            user_info = dhan_login.user_profile(credentials.access_token)
            print(f"  User: {user_info.get('name', 'Unknown')}")
            print("  Status: Valid")
        except Exception:
            print("  Status: Token may be expired")
    else:
        env_token = os.getenv("DHAN_ACCESS_TOKEN")
        if env_token and env_token != "YOUR_ACCESS_TOKEN":
            print("[OK] Using environment variable DHAN_ACCESS_TOKEN")
        else:
            print("[X] Not authenticated")
            print()
            print("Run 'python auth.py' for OAuth login")
            print("Run 'python auth.py --totp' for PIN+TOTP login")


def main():
    """Main entry point for CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        description="DhanHQ Authentication (v2.2.0)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python auth.py           # OAuth login (opens browser)
  python auth.py --totp    # PIN + TOTP login
  python auth.py --renew   # Renew existing token
  python auth.py --status  # Check authentication status
  python auth.py --logout  # Remove saved credentials
        """,
    )
    parser.add_argument(
        "--totp", "-t", action="store_true", help="Use PIN + TOTP authentication"
    )
    parser.add_argument(
        "--renew", "-r", action="store_true", help="Renew existing access token"
    )
    parser.add_argument(
        "--status", "-s", action="store_true", help="Show authentication status"
    )
    parser.add_argument(
        "--logout", "-l", action="store_true", help="Remove saved credentials"
    )

    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.logout:
        clear_credentials()
    elif args.renew:
        renew_token()
    elif args.totp:
        totp_login()
    else:
        oauth_login()


if __name__ == "__main__":
    main()
