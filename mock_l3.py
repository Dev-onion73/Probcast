import glob, json, os

L2_DIR = "data/labeled"
L3_OUT = "data/labeled/l3_mock_batch.jsonl"

batch = []

for fname in glob.glob(f"{L2_DIR}/*.jsonl"):
    with open(fname) as fin:
        for line in fin:
            rec = json.loads(line)
            # Optionally flag as mock/synthetic
            rec["mock_l3"] = True
            batch.append(rec)

with open(L3_OUT, "w") as fout:
    for rec in batch:
        fout.write(json.dumps(rec) + "\n")

print(f"L3 batch file written: {L3_OUT} ({len(batch)} samples)")