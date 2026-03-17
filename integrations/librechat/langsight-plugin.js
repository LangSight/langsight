/**
 * LangSight plugin for LibreChat
 *
 * Intercepts MCP tool calls and sends ToolCallSpans to the LangSight API.
 * Follows the same env-var pattern as the Langfuse integration.
 *
 * Setup:
 *   1. Add to librechat.yaml:
 *        plugins:
 *          - name: langsight
 *            path: ./plugins/langsight-plugin.js
 *
 *   2. Set environment variables:
 *        LANGSIGHT_URL=http://localhost:8000
 *        LANGSIGHT_API_KEY=<optional>
 *        LANGSIGHT_AGENT_NAME=librechat-agent     # optional
 *
 *   3. Restart LibreChat.
 *
 * All MCP tool calls made through LibreChat will now be traced.
 * Fail-open: if LangSight is unreachable, tool calls proceed normally.
 */

'use strict';

const { randomUUID } = require('crypto');

// ---------------------------------------------------------------------------
// Config from env vars
// ---------------------------------------------------------------------------

const LANGSIGHT_URL = (process.env.LANGSIGHT_URL || '').replace(/\/$/, '');
const LANGSIGHT_API_KEY = process.env.LANGSIGHT_API_KEY || null;
const LANGSIGHT_AGENT_NAME = process.env.LANGSIGHT_AGENT_NAME || 'librechat';
const SPANS_ENDPOINT = '/api/traces/spans';
const SEND_TIMEOUT_MS = 3000;

if (!LANGSIGHT_URL) {
  console.warn('[LangSight] LANGSIGHT_URL not set — plugin will not trace tool calls.');
}

// ---------------------------------------------------------------------------
// Span sender (fire-and-forget)
// ---------------------------------------------------------------------------

async function sendSpan(span) {
  if (!LANGSIGHT_URL) return;

  const headers = { 'Content-Type': 'application/json' };
  if (LANGSIGHT_API_KEY) {
    headers['Authorization'] = `Bearer ${LANGSIGHT_API_KEY}`;
  }

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), SEND_TIMEOUT_MS);
    await fetch(`${LANGSIGHT_URL}${SPANS_ENDPOINT}`, {
      method: 'POST',
      headers,
      body: JSON.stringify([span]),
      signal: controller.signal,
    });
    clearTimeout(timeout);
  } catch (err) {
    // Fail-open: log but never throw — monitoring must not break the app
    console.debug(`[LangSight] Failed to send span: ${err.message}`);
  }
}

// ---------------------------------------------------------------------------
// LibreChat plugin hook
// ---------------------------------------------------------------------------

/**
 * LibreChat calls plugin.wrapMCPClient(mcpClient, serverName) to allow
 * plugins to wrap the MCP client before it is used by agents.
 */
function wrapMCPClient(mcpClient, serverName = 'unknown') {
  const original = mcpClient.callTool?.bind(mcpClient);
  if (!original) return mcpClient;

  mcpClient.callTool = async function wrappedCallTool(toolName, args) {
    const startedAt = new Date().toISOString();
    let status = 'success';
    let error = null;

    try {
      const result = await original(toolName, args);
      return result;
    } catch (err) {
      status = err instanceof Error && err.name === 'TimeoutError' ? 'timeout' : 'error';
      error = err?.message || String(err);
      throw err;
    } finally {
      const endedAt = new Date().toISOString();
      const startMs = new Date(startedAt).getTime();
      const endMs = new Date(endedAt).getTime();

      const span = {
        span_id: randomUUID(),
        server_name: serverName,
        tool_name: toolName,
        started_at: startedAt,
        ended_at: endedAt,
        latency_ms: Math.max(0, endMs - startMs),
        status,
        error,
        agent_name: LANGSIGHT_AGENT_NAME,
      };

      // Fire-and-forget — do not await
      sendSpan(span).catch(() => {});
    }
  };

  return mcpClient;
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

module.exports = {
  name: 'langsight',
  version: '0.1.0',
  wrapMCPClient,
};
