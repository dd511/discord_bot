import os
import discord
from discord.ext import commands
from aiohttp import web

# ==========================================
# [설정] 채널 ID 및 역할 ID 설정
# ==========================================
# 감시할 포럼 채널 ID 목록
TARGET_FORUM_CHANNEL_IDS = {
    1550133645338214561,  # 포럼 채널 ID
}

# 제한 없이 포스트를 생성할 수 있는 특정 역할(Role) ID 목록
EXEMPT_ROLE_IDS = {
    1209871328673398864,  # 예외 역할 ID
}

# ==========================================
# [인텐트 설정 및 봇 초기화]
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # 유저 권한/역할 확인용

bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# [Render.com 24시간 유지용 웹 서버 설정]
# ==========================================
async def handle(request):
    return web.Response(text="Bot is running 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# ==========================================
# [이벤트 구동]
# ==========================================
@bot.event
async def on_ready():
    await start_web_server()  # 봇 로그인 시 웹 서버 실행
    print(f"성공적으로 로그인했습니다: {bot.user} (ID: {bot.user.id})")

# 1. 새 포스트(스레드) 생성 시 1인당 1개 제한 검사 (관리자 및 예외 역할 제외)
@bot.event
async def on_thread_create(thread: discord.Thread):
    if isinstance(thread.parent, discord.ForumChannel) and thread.parent_id in TARGET_FORUM_CHANNEL_IDS:
        owner_id = thread.owner_id
        if not owner_id:
            return

        # 작성자의 서버 멤버 객체 가져오기
        member = thread.guild.get_member(owner_id)
        if not member:
            try:
                member = await thread.guild.fetch_member(owner_id)
            except discord.HTTPException:
                member = None

        # [예외 처리] 관리자 권한이 있거나 예외 역할(EXEMPT_ROLE_IDS)을 가진 경우 검사 스킵
        if member:
            is_admin = member.guild_permissions.administrator
            has_exempt_role = any(role.id in EXEMPT_ROLE_IDS for role in member.roles)

            if is_admin or has_exempt_role:
                print(f"[예외 허용] 유저 ID {owner_id} 님은 관리자/예외 역할이므로 제약을 적용하지 않습니다.")
                return

        # 1) 현재 열려있는(Active) 기존 포스트 검사
        active_count = sum(
            1 for t in thread.parent.threads
            if t.owner_id == owner_id and t.id != thread.id
        )

        # 2) 보관된(Archived) 기존 포스트 검사
        archived_count = 0
        try:
            async for archived_thread in thread.parent.archived_threads(limit=None):
                if archived_thread.owner_id == owner_id and archived_thread.id != thread.id:
                    archived_count += 1
                    break
        except Exception as e:
            print(f"보관된 포스트 조회 중 오류 발생: {e}")

        # 제한 초과 시 포스트 자동 삭제
        if (active_count + archived_count) >= 1:
            try:
                owner = await bot.fetch_user(owner_id)
                await owner.send(
                    f"⚠️ **{thread.parent.name}** 채널에는 보관된 포스트를 포함해 1인당 총 1개의 포스트만 생성할 수 있습니다.\n"
                    f"기존에 생성하신 포스트를 이용해 주세요."
                )
            except discord.HTTPException:
                pass

            await thread.delete()
            print(f"[포스트 삭제] 유저 ID {owner_id} 님의 중복 포스트가 삭제되었습니다.")

# 2. 기존 포스트 내 작성자 외 댓글 자동 삭제
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if isinstance(message.channel, discord.Thread):
        thread = message.channel
        if isinstance(thread.parent, discord.ForumChannel) and thread.parent_id in TARGET_FORUM_CHANNEL_IDS:
            if message.author.id != thread.owner_id:
                try:
                    await message.delete()
                    await thread.send(
                        f"{message.author.mention} 님, 이 포스트는 작성자 전용 공간입니다.",
                        delete_after=5
                    )
                except discord.Forbidden:
                    print("봇에 '메시지 관리' 권한이 없어 댓글을 삭제하지 못했습니다.")
                except discord.HTTPException as e:
                    print(f"메시지 삭제 중 오류 발생: {e}")

    await bot.process_commands(message)

# 토큰을 코드에 직접 넣지 않고 환경 변수에서 불러옵니다.
bot.run(os.environ.get("DISCORD_TOKEN"))