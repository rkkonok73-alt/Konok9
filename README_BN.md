# Telegram Multi-Bot Manager — বাংলায়

## Hosting Environment Variables
- `MANAGER_BOT_TOKEN`: BotFather থেকে পাওয়া নতুন Manager Bot Token
- `ADMIN_ID`: আপনার Telegram numeric user ID
- `BOT_DATA_DIR`: ঐচ্ছিক; ডিফল্ট `bot_data`

কোনো Token-ই কোডে বসাবেন না বা GitHub-এ প্রকাশ করবেন না।

## চালানোর কমান্ড
`python manager.py`

## ZIP ফরম্যাট
একটি বট:
```
mybot.zip
  main.py
```
একাধিক বট:
```
bots.zip
  bot_one/main.py
  bot_two/main.py
```

প্রতিটি বটের নিজের `main.py`-তে তার নিজস্ব বটের Token নিরাপদভাবে environment থেকে পড়া উচিত।
এই starter আলাদা per-bot dependency environment তৈরি করে না। `requirements.txt`-এর dependency host-এ আগে প্রস্তুত করতে হবে।

## সতর্কতা
ZIP-এর Python code সার্ভারে arbitrary code চালাতে পারে। শুধু নিজের/বিশ্বস্ত ZIP ব্যবহার করুন। নিরাপদ hosting-এ প্রতিটি bot-কে আলাদা container/VM ও resource/network limits-এ চালানো উচিত।
Free host long-running worker/subprocess নিষিদ্ধ করতে পারে, sleep করতে পারে, বা filesystem মুছে দিতে পারে। Deploy করার আগে hosting-এর বর্তমান সীমাবদ্ধতা যাচাই করুন।
