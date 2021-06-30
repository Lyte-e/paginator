from typing import Union, Optional
from asyncio import TimeoutError

from discord.embeds import _EmptyEmbed
from discord.ext.commands import (
    AutoShardedBot,
    Bot, 
    Context
)
from discord import (
    Reaction, 
    Member, 
    User, 
    Message, 
    Embed,
    errors
)


class _PaginatorBase:
    """Базовый класс Paginator.
    
    Для корректной работы данного класса, надо переопределить методы, 
    прописанные ниже.

    Attributes
    ----------
    STANDART_EMOJIS: :class:`tuple`
        Эмодзи по умолчанию, в формате: 
        `top`, `previous`, `stop`, `next`, `end`
    pages: :class:`dict`
        Список страниц.
    current: :class:`int`
        Текущая страница.

    Parameters
    ----------
    bot: :class:`Bot`
        Экземпляр бота, основное применение - отслеживание действий с реакциями.
    ctx: :class:`Context`
        Контекст, используется для получения информации об авторе 
        и отправки сообщения в текущий чат.
    
    Kwargs
    ------
    emojis: Optional[:class:`tuple`]
        Кортеж с эмодзи, которые будут использоваться в качестве реакций.
        По умолчанию - STANDART_EMOJIS.
    delete_message: Optional[:class:`bool`]
        Нужно ли удалять сообщение, при остановке Paginator 
        или истечении время ожидания. По умолчанию - False.
    cooldown: Union[:class:`int`, :class:`float`]
        Время ожидания (в секундах) добавления реакции к сообщению от пользователя. 
        По умолчанию - 60.
    initial_embed: Optional[:class:`Embed`]
        Embed, который будет выводиться при старте Paginator.
        По умолчанию - первая страница.
    message: Optional[:class:`Message`]
        Сообщение, к которому надо привязать Paginator.
        По умолчанию - новое, в текущем чате.
    
    Methods
    -------
    await start()
        Запускает ивент отслеживания добавления реакций к сообщению.
    await stop()
        Останавливает Paginator и выполняет действие, в зависимости от 
        параметра `delete_message`.
    await paginate_message()
        Привязывает Paginator к конкретному сообщению, либо отправляет новое.
    await pagination(emoji)
        Отвечает за действие, при нажатии реакции под сообщением.
        Для переопределения.
    await generate_embed()
        Генерирует и возвращает Embed в зависимости от текущей страницы
        и предпочтений.
        Для переопределения.
    """
    STANDART_EMOJIS = ("⏪", "◀", "⏹", "▶", "⏩")

    def __init__(self, 
        bot: Union[Bot, AutoShardedBot], 
        context: Context, 
        **kwargs
    ) -> None:
        self.bot = bot
        self.ctx = context

        self.emojis: tuple = kwargs.get("emojis", self.STANDART_EMOJIS)
        self.delete_message: bool = kwargs.get("delete_message", False)
        self.cooldown: Union[int, float] = kwargs.get("cooldown", 60)
        self.initial_embed: Optional[Embed] = kwargs.get("embed", None)
        self.message: Optional[Message] = kwargs.get("message", None)

        self.pages = dict()
        self.current = 0
        
    def __repr__(self) -> str:
        f = "<{0.__class__.__name__} count: {0._count} current: {0.current}"
        return f.format(self)
    
    def __len__(self) -> int:
        """Общее количество текста."""
        return sum(len(p) for p in self.pages.values())

    def __str__(self) -> str:
        """Текст текущей страницы."""
        return self.pages[self._get_page(self.current)]
    
    @property
    def _count(self) -> int:
        """Количество страниц."""
        return len(self.pages)
        
    def _get_page(self, count: int) -> tuple:
        """Получает кортеж с информацией категории из индекса."""
        return tuple(self.pages.keys())[count]
    
    async def _add_reactions(self, *emojis, message: Optional[Message]) -> None:
        """|coro|
        
        Добавляет реакции к определенному сообщению.
        
        Parameters
        ----------
        *emojis
            Список эмодзи для добавления к сообщению в виде реакций.
        message: Optional[:class:`discord.Message`]
            Сообщение, к которому будут добавляться реакции. 
            По умолчанию сообщение пользователя.
        """
        message = message or self.ctx.message
        if message:
            for emoji in emojis:
                await message.add_reaction(emoji)

    def _check(self, reaction: Reaction, user: Union[Member, User]) -> bool:
        """Проверки для метода `wait_for`."""
        return reaction.emoji in self.emojis \
           and user.id == self.ctx.author.id \
           and self.message is not None \
           and reaction.message.id == self.message.id

    async def start(self) -> None:
        """|coro|

        Запускает ивент отслеживания добавления реакций к сообщению.
        
        Основной метод класса.
        """
        message = await self.paginate_message()
        if not message:
            return

        while True:
            try:
                reaction, user = await self.bot.wait_for(
                    "reaction_add", 
                    check=self._check,
                    timeout=self.cooldown
                ) 
            except TimeoutError:
                await self.stop()
            else:
                await self.pagination(str(reaction.emoji))
                await message.remove_reaction(reaction, user)

                embed = await self.generate_embed()
                await self.ctx.send(embed=embed)
        
    async def stop(self) -> None:
        """|coro|
        
        Останавливает Paginator и выполняет действие, в зависимости от 
        параметра `delete_message`."""
        if self.message:
            try:
                if self.delete_message:
                    return await self.message.delete()
                return await self.message.clear_reactions()
            except (errors.NotFound, errors.Forbidden):
                return

    async def paginate_message(self) -> Optional[Message]:
        """|coro|
        
        Привязывает Paginator к конкретному сообщению, либо отправляет новое."""
        if self.initial_embed:
            embed = self.initial_embed
        else:
            embed = await self.generate_embed()

        if self.message:
            message = await self.message.edit(embed=embed)
        else:
            message = await self.ctx.send(embed=embed)
        await self._add_reactions(*self.emojis, message=message)
        self.message = message
        
        return message

    async def pagination(self, emoji: str) -> None:
        """|coro|
        
        Отвечает за действие, при нажатии реакции под сообщением.
        
        Переопределите метод в наследуемом классе.
        """
        return None

    async def generate_embed(self) -> Embed:
        """|coro|
        
        Генерирует и возвращает Embed в зависимости от текущей страницы
        и предпочтений.
        
        Переопределите метод в наследуемом классе."""
        return Embed()


class TextPaginator(_PaginatorBase):
    r"""Стандартный текстовый Paginator с категориями.

    Attributes
    ----------
    category: :class:`int`
        Текущая категория.
    none_types: :class:`tuple`
        Все NoneType виды в Embed.
    
    Parameters [kwargs]
    -------------------
    max_size: :class:`int`
        Максимальное количество символов в описании Embed. По умолчанию - 2000.
    separator: :class:`str`
        Символ, для разделения текста на части. По умолчанию - новая строка (\n).

    Methods
    -------
    cut_text(category, text)
        Разделяет текст на части, не превышающие максимальное 
        количество символов, после добавляет страницу к указанной категории.

        Может подняться ошибка из-за большого количества рекурсий, 
        если текст не может быть разбит на части разделителем.
    add_category(description, title, footer)
        Добавляет категорию к Paginator.
    add_embed(embed)
        Добавляет готовый Embed к Paginator.
    add_from_dict(data)
        Добавляет категорию(-и) через словарь.
    pagination(emoji)
        Отвечает за действие, при нажатии реакции под сообщением.
    generate_embed()
        Генерирует и возвращает Embed в зависимости от текущей страницы.
    """
    def __init__(self, *args, **kwargs) -> None:
        self.max_size: int = kwargs.pop("max_size", 2000)
        self.separator: str = kwargs.pop("separator", "\n")

        self.category = 0
        self.none_types = (None, False, "", Embed.Empty)

        super().__init__(*args, **kwargs)

    def __repr__(self) -> str:
        f = " max_size: {0.max_size} separator: `{0.separator}`"
        return super().__repr__() + f.format(self)
    
    def cut_text(self, category: tuple, text: str) -> None:
        """Разделяет текст на части, не превышающие максимальное 
        количество символов, после добавляет страницу к указанной категории.
        
        Parameters
        ----------
        category: :class:`tuple`
            Кортеж в формате: `заголовок`, `футер`, `порядковый номер`
        text: :clas:`str`
            Текст, для дальнейшего разделения на части.
        """
        sep = self.separator
        split_text = text.strip().split(sep)

        count = len(split_text)
        while len(sep.join(split_text[:count])) > self.max_size:
            count -= 1
        
        self.pages[category].append(sep.join(split_text[:count]))

        leftovers = sep.join(split_text[count:])
        if len(leftovers) > self.max_size:
            self.cut_text(category, leftovers)
        else:
            self.pages[category].append(leftovers)
    
    def add_category(self, 
        description: str, 
        title: Union[str, _EmptyEmbed] = Embed.Empty, 
        footer: Union[str, _EmptyEmbed] = Embed.Empty
    ) -> None:
        """Добавляет категорию к Paginator.
        
        Parameters
        ----------
        description: :class:`str`
            Текст, для разделения.
        title: Union[:class:`str`, :class:`_EmptyEmbed`]
            Заголовок для Embed. По умолчанию - пустой.
        footer: Union[:class:`str`, :class:`_EmptyEmbed`]
            Футер для Embed. По умолчанию - пустой.
        """
        key = (title, footer, self._count)
        self.pages[key] = list()
        self.cut_text(key, description)
    
    def add_embed(self, embed: Embed) -> None:
        """Добавляет готовый Embed к Paginator.
        
        Parameters
        ----------
        embed: :class:`Embed`
            Сгенерированный Embed.
        """
        data = []

        if embed.title:
            data.append(embed.title)
        else:
            if embed.description in self.none_types:
                raise KeyError(
                    "Оба значения title и description не могут быть равны None.")

            data.append(Embed.Empty)
        
        if embed.footer:
            data.append(embed.footer.text)
        else:
            data.append(Embed.Empty)
        
        data.append(self._count)
        self.pages[tuple(data)] = [embed.description]
    
    def add_from_dict(self, data: dict) -> None:
        """Добавляет категорию(-и) через словарь.
        
        Parameters
        ----------
        data: :class:`dict`
            Данные в формате: (`заголовок`, `футер`): [`текст`]
        
        Example
        -------
        add_from_dict({
            ("title", "footer"): ["description"],
            (None, None): ["page-1", "page-2"]
        })
        """
        for category, texts in data.items():
            category = list(category) + [self._count]

            category[0] = category[0] or Embed.Empty
            category[1] = category[1] or Embed.Empty
            
            if len(texts) == 0 or texts[0] in self.none_types:
                texts.append(Embed.Empty)

                if category[0] in self.none_types:
                    raise KeyError(
                        "Оба значения title и description не могут быть равны None.")

            self.pages[tuple(category)] = texts
    
    async def pagination(self, emoji: str) -> None:
        """|coro|
        
        Отвечает за действие, при нажатии реакции под сообщением.
        
        Parameters
        ----------
        emoji: :class:`str`
            Эмодзи, полученное нажатием реакции.
        """
        category_count = self._count - 1
        page_count = len(self.pages[self._get_page(self.category)]) - 1

        if emoji == self.emojis[0] and 0 < self.category:
            self.current = 0
            self.category -= 1

        elif emoji == self.emojis[1] and 0 < self.current:
            self.current -= 1

        elif emoji == self.emojis[2]:
            await self.stop()

        elif emoji == self.emojis[3] and self.current < page_count:
            self.current += 1

        elif emoji == self.emojis[4] and self.category < category_count:
            self.current = 0
            self.category += 1
        
    async def generate_embed(self) -> Embed:
        """|coro|
        
        Генерирует и возвращает Embed в зависимости от текущей страницы."""
        key = self._get_page(self.category)
        page = self.pages[key]
        
        embed = Embed(title=key[0], description=page[self.current])
        embed.set_footer(text=key[1])
        return embed
        
class FieldPaginator(_PaginatorBase):
    """Незаконченный класс. Сделаю, когда вернусь."""
    def __init__(self, **kwargs) -> None:
        self.max_count: int = kwargs.pop("max_count", 25)
