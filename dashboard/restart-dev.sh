#!/bin/bash
# Clean restart the Next.js dev server
kill $(lsof -t -i:3002) 2>/dev/null
sleep 1
rm -rf .next
npx next dev -p 3002
