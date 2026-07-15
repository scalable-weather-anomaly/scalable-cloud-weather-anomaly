#!/bin/bash

CLUSTER_ID="j-U0ZAPP9BBEL3"
REGION="us-east-1"
NODES=$1
STEP_ID=$2

TIMELINE=$(aws emr describe-step \
    --cluster-id $CLUSTER_ID \
    --step-id $STEP_ID \
    --region $REGION \
    --query 'Step.Status.Timeline')

START=$(echo $TIMELINE | python3 -c "import json,sys; t=json.load(sys.stdin); print(t['StartDateTime'])")
END=$(echo $TIMELINE | python3 -c "import json,sys; t=json.load(sys.stdin); print(t['EndDateTime'])")

SECONDS=$(python3 << PYEOF
from datetime import datetime
start = datetime.fromisoformat("$START")
end   = datetime.fromisoformat("$END")
print(int((end - start).total_seconds()))
PYEOF
)

MINUTES=$((SECONDS / 60))
REMAINING=$((SECONDS % 60))

echo "=================================="
echo " Nodes    : $NODES"
echo " Step ID  : $STEP_ID"
echo " Start    : $START"
echo " End      : $END"
echo " Duration : ${MINUTES}m ${REMAINING}s (${SECONDS} seconds)"
echo "=================================="

CSV="benchmarks/results/batch_benchmark.csv"
if [ ! -f "$CSV" ]; then
    echo "nodes,step_id,start,end,seconds,minutes" > $CSV
fi
echo "$NODES,$STEP_ID,$START,$END,$SECONDS,$MINUTES" >> $CSV
echo "Saved to $CSV"
