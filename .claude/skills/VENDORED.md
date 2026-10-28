# Vendored Hugging Face skills

Skills in this directory (except any added later by us) are copied from
https://github.com/huggingface/skills (Apache-2.0, see LICENSE.huggingface-skills)
at commit fabc634a893f62ad5c2039830397efa35fa62715 (2026-10-23).

Update:

    git clone --depth 1 https://github.com/huggingface/skills /tmp/hfskills
    cp -r /tmp/hfskills/skills/* .claude/skills/

Note: most skills need network access to huggingface.co (and the `hf` CLI / `huggingface_hub`).
