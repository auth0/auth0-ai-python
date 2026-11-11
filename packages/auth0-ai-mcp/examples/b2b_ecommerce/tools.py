"""Tools for the B2B ecommerce server.

The flagship `cancel_and_refund_order` spans two services. It gates on the caller's
incoming scopes, then mints one downstream token per service. Each token comes from
`get_token_on_behalf_of`, which reuses a cached token on later calls when the client has a
token store, and exchanges on every call when it does not.

To call a third-party API such as Google, see "Try Token Vault" in the README.
"""

import os

from mcp.server.mcpserver import MCPServer

from auth0_ai_mcp import require_caller_mcp_client, with_required_scopes

ORDERS_AUDIENCE = os.environ["ORDERS_AUDIENCE"]
PAYMENTS_AUDIENCE = os.environ["PAYMENTS_AUDIENCE"]
INVENTORY_AUDIENCE = os.environ["INVENTORY_AUDIENCE"]
SHIPPING_AUDIENCE = os.environ["SHIPPING_AUDIENCE"]
CUSTOMERS_AUDIENCE = os.environ["CUSTOMERS_AUDIENCE"]
NOTIFICATIONS_AUDIENCE = os.environ["NOTIFICATIONS_AUDIENCE"]
ANALYTICS_AUDIENCE = os.environ["ANALYTICS_AUDIENCE"]


def register_tools(mcp: MCPServer) -> None:
    @mcp.tool(
        name="cancel_and_refund_order",
        title="Cancel and Refund Order",
        description="Cancels an order and refunds its payment in one step.",
        annotations={"destructiveHint": True},
    )
    @with_required_scopes("tool:cancel_and_refund_order")
    async def cancel_and_refund_order(order_id: str, amount: str) -> str:
        auth0 = require_caller_mcp_client()
        orders_token = await auth0.get_token_on_behalf_of(
            audience=ORDERS_AUDIENCE, scope="cancel:orders"
        )
        payments_token = await auth0.get_token_on_behalf_of(
            audience=PAYMENTS_AUDIENCE, scope="refund:payments"
        )
        _ = (orders_token, payments_token)
        return f"Order {order_id} cancelled and {amount} refunded (demo, no real change made)"

    @mcp.tool(
        name="fulfill_order",
        title="Fulfill Order",
        description="Reserves inventory, creates a shipment, and sends a fulfillment notification.",
        annotations={"destructiveHint": True},
    )
    @with_required_scopes("tool:fulfill_order")
    async def fulfill_order(order_id: str) -> str:
        auth0 = require_caller_mcp_client()
        orders_token = await auth0.get_token_on_behalf_of(
            audience=ORDERS_AUDIENCE, scope="read:orders"
        )
        inventory_token = await auth0.get_token_on_behalf_of(
            audience=INVENTORY_AUDIENCE, scope="read:inventory write:inventory"
        )
        shipping_token = await auth0.get_token_on_behalf_of(
            audience=SHIPPING_AUDIENCE, scope="read:shipments create:shipments"
        )
        notifications_token = await auth0.get_token_on_behalf_of(
            audience=NOTIFICATIONS_AUDIENCE, scope="send:notifications"
        )
        _ = (orders_token, inventory_token, shipping_token, notifications_token)
        return f"Order {order_id} fulfilled (demo, no real change made)"

    @mcp.tool(
        name="order_status_report",
        title="Order Status Report",
        description="Returns a summary of order, inventory, shipment, and customer status.",
        annotations={"readOnlyHint": True},
    )
    @with_required_scopes("tool:order_status_report")
    async def order_status_report(order_id: str) -> str:
        auth0 = require_caller_mcp_client()
        orders_token = await auth0.get_token_on_behalf_of(
            audience=ORDERS_AUDIENCE, scope="read:orders"
        )
        inventory_token = await auth0.get_token_on_behalf_of(
            audience=INVENTORY_AUDIENCE, scope="read:inventory"
        )
        shipping_token = await auth0.get_token_on_behalf_of(
            audience=SHIPPING_AUDIENCE, scope="read:shipments"
        )
        customers_token = await auth0.get_token_on_behalf_of(
            audience=CUSTOMERS_AUDIENCE, scope="read:customers"
        )
        _ = (orders_token, inventory_token, shipping_token, customers_token)
        return f"Status report for order {order_id} (demo, no real data)"

    @mcp.tool(
        name="update_customer_and_notify",
        title="Update Customer and Notify",
        description="Updates customer data and sends a notification.",
        annotations={"destructiveHint": True},
    )
    @with_required_scopes("tool:update_customer_and_notify")
    async def update_customer_and_notify(customer_id: str) -> str:
        auth0 = require_caller_mcp_client()
        customers_token = await auth0.get_token_on_behalf_of(
            audience=CUSTOMERS_AUDIENCE, scope="read:customers write:customers"
        )
        notifications_token = await auth0.get_token_on_behalf_of(
            audience=NOTIFICATIONS_AUDIENCE, scope="send:notifications"
        )
        _ = (customers_token, notifications_token)
        return f"Customer {customer_id} updated and notified (demo, no real change made)"

    @mcp.tool(
        name="sales_analytics_report",
        title="Sales Analytics Report",
        description="Returns aggregated sales analytics using a service-to-service token.",
        annotations={"readOnlyHint": True},
    )
    @with_required_scopes("tool:sales_analytics_report")
    async def sales_analytics_report() -> str:
        auth0 = require_caller_mcp_client()
        token = await auth0.get_client_credentials_token(
            audience=ANALYTICS_AUDIENCE, scope="read:analytics"
        )
        _ = token
        return "Monthly revenue: $142,000 | Top product: Enterprise Suite"
