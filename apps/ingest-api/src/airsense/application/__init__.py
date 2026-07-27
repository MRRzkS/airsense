"""Use cases and orchestration.

Depends on `domain` and on the Protocols declared in `application.ports`. It
never imports a concrete adapter; `infrastructure` implements the ports and
`api` wires the two together.
"""
