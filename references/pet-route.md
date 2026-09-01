# Codex 桌面宠物分支

仅当用户明确说要“Codex 宠物 / 桌面宠物 / pet”时执行。

1. 先完成并验证九张 GIF。
2. 运行：

```bash
python3 scripts/prepare_pet_handoff.py \
  --gif-dir /absolute/path/to/job/gifs \
  --output /absolute/path/to/job/pet-source-map.json
```

3. 检查自动状态建议。默认九种语义映射为：`idle`、`walk`、`run`、`happy`、`sad`、`celebrate`、`work`、`sleep`、`alert`；用户给出的动作语义优先，允许覆盖。
4. 使用当前环境的 `hatch-pet` skill，将这些 GIF 当作动作/风格参考，而不是直接冒充完整宠物表。该技能负责 v2 宠物要求：九条标准动画行、16 个 look 方向、确定性拼装、预览与视觉 QA。
5. 宠物包与表情包 ZIP 分开交付，不能把未完成的九 GIF 映射称作已完成宠物。
