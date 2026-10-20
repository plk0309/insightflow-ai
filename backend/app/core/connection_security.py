
import ipaddress
import socket


class UnsafeDatabaseHostError(ValueError):
    """Raised when a database host is not an approved public destination."""


def validate_database_host(host: str) -> str:
    """
    Validate a PostgreSQL host before a connection attempt.

    This is a preliminary check only. The connection layer must
    connect to the validated IP rather than resolving the hostname
    again, to prevent DNS rebinding.
    """
    if not isinstance(host, str):
        raise UnsafeDatabaseHostError("Invalid database host")

    host = host.strip()

    if not host or len(host) > 253:
        raise UnsafeDatabaseHostError("Invalid database host")

    # Reject URLs, credentials, paths, IPv6 zone identifiers,
    # and malformed hostnames.
    if any(char in host for char in ("/", "\\", "@", "%", "?", "#")):
        raise UnsafeDatabaseHostError("Invalid database host")

    # Accept bracketed IPv6 literals for validation.
    lookup_host = host
    if host.startswith("[") and host.endswith("]"):
        lookup_host = host[1:-1]

    try:
        addresses = [
            ipaddress.ip_address(lookup_host)
        ]
    except ValueError:
        try:
            results = socket.getaddrinfo(
                lookup_host,
                None,
                type=socket.SOCK_STREAM,
            )
        except (socket.gaierror, UnicodeError, OSError) as exc:
            raise UnsafeDatabaseHostError(
                "Database host could not be resolved"
            ) from exc

        addresses = []

        for result in results:
            try:
                addresses.append(
                    ipaddress.ip_address(result[4][0])
                )
            except ValueError as exc:
                raise UnsafeDatabaseHostError(
                    "Invalid resolved database address"
                ) from exc

    if not addresses:
        raise UnsafeDatabaseHostError(
            "Database host has no resolved addresses"
        )

    for address in addresses:
        if not address.is_global:
            raise UnsafeDatabaseHostError(
                "Database host resolves to a restricted IP address"
            )

    return host

def resolve_public_database_addresses(host: str) -> tuple[str, ...]:
    """
    Resolve a database host to approved public IP addresses.

    This function performs DNS resolution and returns validated
    addresses for a future connection layer to use directly.

    IMPORTANT: The connection layer must not resolve the original
    hostname again after calling this function.
    """
    if not isinstance(host, str):
        raise UnsafeDatabaseHostError("Invalid database host")

    host = host.strip()

    if not host or len(host) > 253:
        raise UnsafeDatabaseHostError("Invalid database host")

    if any(char in host for char in ("/", "\\", "@", "%", "?", "#")):
        raise UnsafeDatabaseHostError("Invalid database host")

    lookup_host = host
    if host.startswith("[") and host.endswith("]"):
        lookup_host = host[1:-1]

    try:
        address = ipaddress.ip_address(lookup_host)
        addresses = [address]
    except ValueError:
        try:
            results = socket.getaddrinfo(
                lookup_host,
                None,
                type=socket.SOCK_STREAM,
            )
        except (socket.gaierror, UnicodeError, OSError) as exc:
            raise UnsafeDatabaseHostError(
                "Database host could not be resolved"
            ) from exc

        addresses = []

        for result in results:
            try:
                addresses.append(
                    ipaddress.ip_address(result[4][0])
                )
            except ValueError as exc:
                raise UnsafeDatabaseHostError(
                    "Invalid resolved database address"
                ) from exc

    if not addresses:
        raise UnsafeDatabaseHostError(
            "Database host has no resolved addresses"
        )

    for address in addresses:
        if not address.is_global:
            raise UnsafeDatabaseHostError(
                "Database host resolves to a restricted IP address"
            )

    # Remove duplicates while preserving resolution order.
    return tuple(dict.fromkeys(str(address) for address in addresses))
