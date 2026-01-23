"""LDAP/AD authentication and group sync service."""
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import LdapConfig, User, UserGroup, UserGroupMember
from src.utils.crypto import decrypt_value

logger = logging.getLogger(__name__)


@dataclass
class LdapUser:
    """User info from LDAP."""

    username: str
    email: str | None
    display_name: str | None
    dn: str
    groups: list[str]


class LdapService:
    """Service for LDAP authentication and user/group sync."""

    async def authenticate(
        self,
        db: AsyncSession,
        username: str,
        password: str,
    ) -> LdapUser | None:
        """Authenticate user against configured LDAP servers.

        Args:
            db: Database session.
            username: Username to authenticate.
            password: Password to verify.

        Returns:
            LdapUser if authentication succeeds, None otherwise.
        """
        try:
            from ldap3 import Server, Connection, ALL, SUBTREE, SIMPLE
        except ImportError:
            logger.warning("ldap3 not installed, LDAP authentication disabled")
            return None

        # Get active LDAP configs, primary first
        result = await db.execute(
            select(LdapConfig)
            .where(LdapConfig.is_active == True)  # noqa: E712
            .order_by(LdapConfig.is_primary.desc())
        )
        configs = result.scalars().all()

        if not configs:
            logger.debug("No active LDAP configurations")
            return None

        for config in configs:
            user = await self._authenticate_with_config(config, username, password)
            if user:
                return user

        return None

    async def _authenticate_with_config(
        self,
        config: LdapConfig,
        username: str,
        password: str,
    ) -> LdapUser | None:
        """Authenticate against a specific LDAP config.

        Args:
            config: LDAP configuration to use.
            username: Username to authenticate.
            password: Password to verify.

        Returns:
            LdapUser if authentication succeeds, None otherwise.
        """
        try:
            from ldap3 import Server, Connection, ALL, SUBTREE, SIMPLE
            from ldap3.core.exceptions import LDAPException

            # Setup server
            server = Server(
                config.server_url,
                use_ssl=config.use_ssl,
                get_info=ALL,
            )

            # First bind with service account to search for user
            bind_password = decrypt_value(config.bind_password_encrypted)
            search_conn = Connection(
                server,
                user=config.bind_dn,
                password=bind_password,
                authentication=SIMPLE,
                auto_bind=True,
            )

            if config.use_start_tls:
                search_conn.start_tls()

            # Search for user
            search_filter = config.user_search_filter.format(username=username)
            search_conn.search(
                config.base_dn,
                search_filter,
                search_scope=SUBTREE,
                attributes=[
                    config.username_attribute,
                    config.email_attribute,
                    config.display_name_attribute,
                    config.group_attribute,
                ],
            )

            if not search_conn.entries:
                search_conn.unbind()
                return None

            user_entry = search_conn.entries[0]
            user_dn = user_entry.entry_dn
            search_conn.unbind()

            # Now bind as the user to verify password
            user_conn = Connection(
                server,
                user=user_dn,
                password=password,
                authentication=SIMPLE,
            )

            if not user_conn.bind():
                return None

            user_conn.unbind()

            # Extract user info
            groups = []
            if config.group_attribute in user_entry:
                groups = [str(g) for g in user_entry[config.group_attribute]]

            return LdapUser(
                username=str(user_entry[config.username_attribute]),
                email=str(user_entry[config.email_attribute])
                if config.email_attribute in user_entry
                else None,
                display_name=str(user_entry[config.display_name_attribute])
                if config.display_name_attribute in user_entry
                else None,
                dn=user_dn,
                groups=groups,
            )

        except LDAPException as e:
            logger.error(f"LDAP error with {config.name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during LDAP auth: {e}")
            return None

    async def sync_user_groups(
        self,
        db: AsyncSession,
        user: User,
        ldap_groups: list[str],
    ) -> None:
        """Sync LDAP groups to PureBoot UserGroups.

        This updates the user's group memberships to match their LDAP groups.
        Only affects groups that have an ldap_group_dn mapping configured.

        Args:
            db: Database session.
            user: The user to sync groups for.
            ldap_groups: List of LDAP group DNs the user belongs to.
        """
        # Get all user groups with LDAP DN mappings
        result = await db.execute(
            select(UserGroup).where(UserGroup.ldap_group_dn.isnot(None))
        )
        mapped_groups = result.scalars().all()

        # Build set of group IDs user should be in
        target_group_ids = set()
        for group in mapped_groups:
            if group.ldap_group_dn in ldap_groups:
                target_group_ids.add(group.id)

        # Get current memberships
        result = await db.execute(
            select(UserGroupMember).where(UserGroupMember.user_id == user.id)
        )
        current_memberships = result.scalars().all()
        current_group_ids = {m.user_group_id for m in current_memberships}

        # Add missing memberships
        for group_id in target_group_ids - current_group_ids:
            db.add(UserGroupMember(user_id=user.id, user_group_id=group_id))

        # Remove stale memberships (only for LDAP-mapped groups)
        ldap_mapped_ids = {g.id for g in mapped_groups}
        for membership in current_memberships:
            if (
                membership.user_group_id in ldap_mapped_ids
                and membership.user_group_id not in target_group_ids
            ):
                await db.delete(membership)


ldap_service = LdapService()
