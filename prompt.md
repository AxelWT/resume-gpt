**《AI面试教练》**

**作用：**在收到面试邀请的时候，进行辅助提升能力的辅助工具

**用户输入：** 

- 模型供应商的 base_url api_key model_name
- 牛客网搜索词(公司+岗位)
- PDF简历
- 选择分析模块（面经总结与考点分析，模拟面试题目预测，简历优化建议）
- 高级选项（最大抓取面经数量）

**功能：**

- 全程使用指定供应商的模型进行AI提供
- 根据用户输入的牛客网搜索词(公司+岗位)，进行相关面经数量爬取
- 根据面经以及选择分析模块，使用AI进行相关面试分析报告
- 生成面试分析报告
- 在右侧侧边栏也可以看到原始问题题库

**语言：**

- 后端采用python，前端使用html

给你的参考图如附件，只参考框架等相关内容

模型调用示例：
curl -X POST "https://open.bigmodel.cn/api/paas/v4/chat/completions" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer your-api-key" \
    -d '{
        "model": "glm-4.6",
        "messages": [
        {
            "role": "user",
            "content": "作为一名营销专家，请为我的产品创作一个吸引人的口号"
        },
        {
            "role": "assistant",
            "content": "当然，要创作一个吸引人的口号，请告诉我一些关于您产品的信息"
        },
        {
            "role": "user",
            "content": "智谱AI 开放平台"
        }
            ],
            "thinking": {
            "type": "enabled"
        },
            "max_tokens": 65536,
            "temperature": 1.0
        }'
