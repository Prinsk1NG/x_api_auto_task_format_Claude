name: 硅谷情报局 (V10.11)

on:
  schedule:
    - cron: '0 0 * * *' # 北京时间早上 8:00
  workflow_dispatch:
    inputs:
      test_mode:
        description: '测试模式？(true 拦截主群 / false 全量发送)'
        required: true
        default: 'false'

permissions:
  contents: write

jobs:
  build-and-run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install
        run: pip install requests xai-sdk
        
      - name: Run
        env:
          twitterapi_io_KEY: ${{ secrets.TWITTERAPI_IO_KEY }}
          XAI_API_KEY: ${{ secrets.XAI_API_KEY }}
          PPLX_API_KEY: ${{ secrets.PPLX_API_KEY }}
          TAVILY_API_KEY: ${{ secrets.TAVILY_API_KEY }}
          SF_API_KEY: ${{ secrets.SF_API_KEY }}
          IMGBB_API_KEY: ${{ secrets.IMGBB_API_KEY }}
          FEISHU_WEBHOOK_URL: ${{ secrets.FEISHU_WEBHOOK_URL }}
          FEISHU_WEBHOOK_URL_1: ${{ secrets.FEISHU_WEBHOOK_URL_1 }}
          TEST_MODE_ENV: ${{ github.event.inputs.test_mode || 'false' }}
        run: python x_api_auto_task_xai_xml.py

      - name: Save
        run: |
          git config --local user.email "actions@github.com"
          git config --local user.name "Github-Bot"
          git add data/
          git commit -m "🤖 Archive Intelligence" || echo "No changes"
          git push
