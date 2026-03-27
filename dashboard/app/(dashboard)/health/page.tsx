// Tool Health has been merged into MCP Servers (/servers).
// This redirect preserves bookmarks and any external links.
import { redirect } from "next/navigation";

export default function HealthRedirect() {
  redirect("/servers");
}
