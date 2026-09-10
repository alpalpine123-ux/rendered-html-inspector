import time

import streamlit as st

from bs4 import BeautifulSoup, Comment

from selenium import webdriver
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.support.ui import WebDriverWait


# =========================================
# Configuration
# =========================================

CUSTOM_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36 "
    "MyStreamlitApp/1.0"
)

PAGE_LOAD_TIMEOUT = 90
IMPLICIT_WAIT = 3

SMART_WAIT_TIMEOUT = 50
STABILITY_WINDOW = 4.0
POLL_INTERVAL = 0.5

MAX_TEXT_PREVIEW_CHARS = 30000
MAX_HTML_RETURN_CHARS = 500000
MAX_PRETTY_HTML_RETURN_CHARS = 300000


# =========================================
# Page configuration
# =========================================

st.set_page_config(
    page_title="Rendered HTML Inspector",
    page_icon="🌐",
    layout="wide",
)


# =========================================
# URL helper
# =========================================

def normalize_url(url: str) -> str:

    url = (url or "").strip()

    if not url:
        return ""

    if not url.startswith(
        ("http://", "https://")
    ):
        url = "https://" + url

    return url


# =========================================
# HTML helpers
# =========================================

def parse_html(html: str):

    for parser in [
        "lxml",
        "html.parser",
    ]:

        try:
            return BeautifulSoup(
                html,
                parser
            )

        except Exception:
            continue

    raise RuntimeError(
        "No valid HTML parser is available."
    )


def truncate_text(
    value: str,
    max_len: int
) -> str:

    if not value:
        return ""

    if len(value) <= max_len:
        return value

    return value[:max_len]


# =========================================
# Selenium / Chromium
# =========================================

def create_driver():

    chrome_options = webdriver.ChromeOptions()

    # Headless browser
    chrome_options.add_argument(
        "--headless=new"
    )

    # Required in Linux containers
    chrome_options.add_argument(
        "--no-sandbox"
    )

    chrome_options.add_argument(
        "--disable-dev-shm-usage"
    )

    chrome_options.add_argument(
        "--disable-gpu"
    )

    chrome_options.add_argument(
        "--disable-software-rasterizer"
    )

    chrome_options.add_argument(
        "--disable-extensions"
    )

    chrome_options.add_argument(
        "--disable-background-networking"
    )

    chrome_options.add_argument(
        "--disable-sync"
    )

    chrome_options.add_argument(
        "--disable-features=Translate"
    )

    chrome_options.add_argument(
        "--window-size=1280,720"
    )

    chrome_options.add_argument(
        f"--user-agent={CUSTOM_USER_AGENT}"
    )

    # Chromium location on Linux
    chrome_options.binary_location = (
        "/usr/bin/chromium"
    )

    driver = webdriver.Chrome(
        options=chrome_options
    )

    driver.set_page_load_timeout(
        PAGE_LOAD_TIMEOUT
    )

    driver.implicitly_wait(
        IMPLICIT_WAIT
    )

    return driver


# =========================================
# Page state
# =========================================

def get_page_state(driver):

    script = """
    return {
        readyState: document.readyState,
        title: document.title || "",
        url: location.href || "",

        bodyExists: !!document.body,

        bodyTextLength:
            document.body
                ? document.body.innerText.length
                : 0,

        htmlLength:
            document.documentElement
                ? document.documentElement.outerHTML.length
                : 0,

        scrollHeight:
            document.body
                ? document.body.scrollHeight
                : 0,

        imgTotal:
            document.images
                ? document.images.length
                : 0,

        imgLoaded:
            document.images
                ? Array.from(document.images)
                    .filter(img => img.complete)
                    .length
                : 0,

        scriptCount:
            document.scripts
                ? document.scripts.length
                : 0
    };
    """

    return driver.execute_script(
        script
    )


# =========================================
# DOM ready
# =========================================

def wait_for_dom_ready(
    driver,
    timeout=25
):

    WebDriverWait(
        driver,
        timeout
    ).until(
        lambda d:
        d.execute_script(
            "return document.readyState"
        )
        in [
            "interactive",
            "complete",
        ]
    )


# =========================================
# Visual stability
# =========================================

def wait_for_visual_stability(
    driver,
    timeout=SMART_WAIT_TIMEOUT,
    stable_window=STABILITY_WINDOW,
    poll=POLL_INTERVAL,
):

    end_time = (
        time.time()
        + timeout
    )

    stable_since = None
    last_signature = None

    samples = []

    while time.time() < end_time:

        try:

            state = get_page_state(
                driver
            )

            signature = (
                state["readyState"],
                state["htmlLength"],
                state["bodyTextLength"],
                state["scrollHeight"],
                state["imgLoaded"],
                state["imgTotal"],
                state["title"],
                state["url"],
            )

            samples.append(state)

            if len(samples) > 8:
                samples.pop(0)

            has_body = (
                state["bodyExists"]
            )

            is_complete = (
                state["readyState"]
                == "complete"
            )

            if (
                has_body
                and is_complete
                and signature == last_signature
            ):

                if stable_since is None:
                    stable_since = time.time()

                if (
                    time.time()
                    - stable_since
                    >= stable_window
                ):

                    return {
                        "stable": True,
                        "last_state": state,
                        "samples": samples,
                    }

            else:

                stable_since = None

            last_signature = signature

            time.sleep(poll)

        except Exception:

            time.sleep(poll)

    try:

        return {
            "stable": False,
            "last_state":
                get_page_state(driver),
            "samples": samples,
        }

    except Exception:

        return {
            "stable": False,
            "last_state": {},
            "samples": samples,
        }


# =========================================
# Smooth scroll
# =========================================

def smooth_scroll_page(driver):

    try:

        total_height = driver.execute_script(
            """
            return document.body
                ? document.body.scrollHeight
                : 0
            """
        )

        if (
            not total_height
            or total_height <= 0
        ):
            return

        current = 0

        step = 700

        last_height = total_height

        while current < last_height:

            driver.execute_script(
                f"window.scrollTo(0, {current});"
            )

            time.sleep(0.35)

            current += step

            try:

                new_height = driver.execute_script(
                    """
                    return document.body
                        ? document.body.scrollHeight
                        : 0
                    """
                )

                if new_height > last_height:
                    last_height = new_height

            except Exception:
                pass

        driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight);"
        )

        time.sleep(0.6)

        driver.execute_script(
            "window.scrollTo(0, 0);"
        )

        time.sleep(0.4)

    except Exception:
        pass


# =========================================
# Pretty HTML
# =========================================

def build_pretty_html(
    html: str
):

    try:

        soup = parse_html(
            html
        )

        return soup.prettify()

    except Exception:

        return html


# =========================================
# DOM outline
# =========================================

def build_dom_outline(
    element,
    depth=0,
    max_depth=5,
    max_children=15,
):

    if depth > max_depth:
        return []

    outline = []

    children = [
        child
        for child in element.children
        if getattr(
            child,
            "name",
            None
        )
    ]

    for child in children[
        :max_children
    ]:

        attrs = []

        if child.get("id"):

            attrs.append(
                f'id="{child.get("id")}"'
            )

        if child.get("class"):

            attrs.append(
                f'class="{" ".join(child.get("class"))}"'
            )

        attr_text = (
            f" [{' | '.join(attrs)}]"
            if attrs
            else ""
        )

        line = (
            f'{"  " * depth}'
            f'- <{child.name}>'
            f'{attr_text}'
        )

        outline.append(
            line
        )

        outline.extend(
            build_dom_outline(
                child,
                depth + 1,
                max_depth,
                max_children,
            )
        )

    return outline


# =========================================
# HTML analysis
# =========================================

def analyze_html_structured(
    html: str
):

    soup = parse_html(
        html
    )

    comments = soup.find_all(
        string=lambda text:
        isinstance(
            text,
            Comment
        )
    )

    title = (
        soup.title.get_text(
            strip=True
        )
        if soup.title
        else ""
    )

    # -------------------------------------
    # Meta description
    # -------------------------------------

    meta_description = ""

    meta_desc_tag = soup.find(
        "meta",
        attrs={
            "name": "description"
        },
    )

    if (
        meta_desc_tag
        and meta_desc_tag.get(
            "content"
        )
    ):

        meta_description = (
            meta_desc_tag[
                "content"
            ].strip()
        )

    # -------------------------------------
    # Canonical
    # -------------------------------------

    canonical = ""

    canonical_tag = soup.find(
        "link",
        attrs={
            "rel":
                lambda x:
                x
                and "canonical"
                in x
        },
    )

    if (
        canonical_tag
        and canonical_tag.get(
            "href"
        )
    ):

        canonical = (
            canonical_tag[
                "href"
            ].strip()
        )

    # -------------------------------------
    # Headings
    # -------------------------------------

    headings = {}

    for level in [
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    ]:

        headings[level] = [
            tag.get_text(
                " ",
                strip=True
            )
            for tag in soup.find_all(
                level
            )
        ]

    # -------------------------------------
    # Semantic sections
    # -------------------------------------

    semantic_sections = {

        "header":
            len(
                soup.find_all(
                    "header"
                )
            ),

        "nav":
            len(
                soup.find_all(
                    "nav"
                )
            ),

        "main":
            len(
                soup.find_all(
                    "main"
                )
            ),

        "section":
            len(
                soup.find_all(
                    "section"
                )
            ),

        "article":
            len(
                soup.find_all(
                    "article"
                )
            ),

        "aside":
            len(
                soup.find_all(
                    "aside"
                )
            ),

        "footer":
            len(
                soup.find_all(
                    "footer"
                )
            ),
    }

    # -------------------------------------
    # Forms
    # -------------------------------------

    forms = []

    for form in soup.find_all(
        "form"
    ):

        forms.append({

            "action":
                form.get(
                    "action",
                    ""
                ),

            "method":
                (
                    form.get(
                        "method",
                        ""
                    )
                    or ""
                ).lower(),

            "id":
                form.get(
                    "id",
                    ""
                ),

            "class":
                (
                    " ".join(
                        form.get(
                            "class",
                            []
                        )
                    )
                    if form.get(
                        "class"
                    )
                    else ""
                ),

            "inputs":
                len(
                    form.find_all(
                        "input"
                    )
                ),

            "buttons":
                len(
                    form.find_all(
                        "button"
                    )
                ),

            "textareas":
                len(
                    form.find_all(
                        "textarea"
                    )
                ),

            "selects":
                len(
                    form.find_all(
                        "select"
                    )
                ),
        })

    # -------------------------------------
    # Tables
    # -------------------------------------

    tables = []

    for table in soup.find_all(
        "table"
    ):

        tables.append({

            "rows":
                len(
                    table.find_all(
                        "tr"
                    )
                ),

            "headers":
                len(
                    table.find_all(
                        "th"
                    )
                ),

            "cells":
                len(
                    table.find_all(
                        "td"
                    )
                ),
        })

    # -------------------------------------
    # Links
    # -------------------------------------

    top_links = []

    for a in soup.find_all(
        "a",
        href=True
    )[:50]:

        top_links.append({

            "text":
                a.get_text(
                    " ",
                    strip=True
                )[:150],

            "href":
                a.get(
                    "href",
                    ""
                ),
        })

    # -------------------------------------
    # Images
    # -------------------------------------

    top_images = []

    for img in soup.find_all(
        "img"
    )[:50]:

        top_images.append({

            "src":
                img.get(
                    "src",
                    ""
                ),

            "alt":
                img.get(
                    "alt",
                    ""
                ),

            "width":
                img.get(
                    "width",
                    ""
                ),

            "height":
                img.get(
                    "height",
                    ""
                ),
        })

    # -------------------------------------
    # JSON-LD
    # -------------------------------------

    scripts = soup.find_all(
        "script"
    )

    json_ld_blocks = []

    for script in scripts:

        if (
            script.get("type")
            == "application/ld+json"
        ):

            content = (
                script.string.strip()
                if script.string
                else script.get_text(
                    strip=True
                )
            )

            if content:

                json_ld_blocks.append(
                    content[:5000]
                )

    # -------------------------------------
    # DOM outline
    # -------------------------------------

    body = (
        soup.body
        if soup.body
        else soup
    )

    dom_outline = build_dom_outline(
        body,
        max_depth=5,
        max_children=15,
    )

    # -------------------------------------
    # Pretty HTML
    # -------------------------------------

    pretty_html = build_pretty_html(
        html
    )

    # -------------------------------------
    # HEAD / BODY / MAIN
    # -------------------------------------

    head_html = ""
    body_html = ""
    main_html = ""

    if soup.head:

        head_html = (
            soup.head.prettify()
        )

    if soup.body:

        body_html = (
            soup.body.prettify()
        )

    main_tag = soup.find(
        "main"
    )

    if main_tag:

        main_html = (
            main_tag.prettify()
        )

    # -------------------------------------
    # Return
    # -------------------------------------

    return {

        "document": {

            "title": title,

            "meta_description":
                meta_description,

            "canonical":
                canonical,

            "html_length":
                len(html),

            "comments_count":
                len(comments),

            "scripts_count":
                len(scripts),

            "styles_count":
                len(
                    soup.find_all(
                        "style"
                    )
                ),

            "links_count":
                len(
                    soup.find_all(
                        "a"
                    )
                ),

            "images_count":
                len(
                    soup.find_all(
                        "img"
                    )
                ),

            "forms_count":
                len(
                    soup.find_all(
                        "form"
                    )
                ),

            "tables_count":
                len(
                    soup.find_all(
                        "table"
                    )
                ),
        },

        "headings":
            headings,

        "semantic_sections":
            semantic_sections,

        "forms":
            forms,

        "tables":
            tables,

        "top_links":
            top_links,

        "top_images":
            top_images,

        "json_ld_blocks":
            json_ld_blocks,

        "dom_outline":
            dom_outline,

        "pretty_html":
            truncate_text(
                pretty_html,
                MAX_PRETTY_HTML_RETURN_CHARS,
            ),

        "head_html":
            head_html,

        "body_html":
            body_html,

        "main_html":
            main_html,

        "text_preview":
            truncate_text(
                soup.get_text(
                    "\n",
                    strip=True
                ),
                MAX_TEXT_PREVIEW_CHARS,
            ),
    }


# =========================================
# Main Selenium fetcher
# =========================================

def fetch_page_data(
    url: str
):

    driver = None

    try:

        driver = create_driver()

        driver.get(
            url
        )

        wait_for_dom_ready(
            driver,
            timeout=25
        )

        initial_stability = (
            wait_for_visual_stability(
                driver,
                timeout=20,
                stable_window=2.0,
            )
        )

        smooth_scroll_page(
            driver
        )

        final_stability = (
            wait_for_visual_stability(
                driver,
                timeout=SMART_WAIT_TIMEOUT,
                stable_window=STABILITY_WINDOW,
            )
        )

        final_html = (
            driver.page_source
        )

        final_title = (
            driver.title
        )

        final_url = (
            driver.current_url
        )

        screenshot_png = (
            driver.get_screenshot_as_png()
        )

        page_state = (
            get_page_state(
                driver
            )
        )

        html_analysis = (
            analyze_html_structured(
                final_html
            )
        )

        return {

            "success": True,

            "title":
                final_title,

            "current_url":
                final_url,

            "html":
                truncate_text(
                    final_html,
                    MAX_HTML_RETURN_CHARS,
                ),

            "html_analysis":
                html_analysis,

            "screenshot_png":
                screenshot_png,

            "page_state":
                page_state,

            "initial_stability":
                initial_stability,

            "final_stability":
                final_stability,
        }

    except TimeoutException:

        return {

            "success": False,

            "error":
                "Page load timeout: "
                "loading the page exceeded "
                "the allowed time.",
        }

    except WebDriverException as e:

        return {

            "success": False,

            "error":
                f"WebDriver error: {str(e)}",
        }

    except Exception as e:

        return {

            "success": False,

            "error":
                f"Unexpected error: {str(e)}",
        }

    finally:

        if driver:

            try:
                driver.quit()

            except Exception:
                pass


# =========================================
# Streamlit UI
# =========================================

st.title(
    "🌐 Rendered HTML Inspector"
)

st.write(
    "URL را وارد کنید تا صفحه با "
    "Selenium و Chromium مستقیماً "
    "روی Streamlit Cloud رندر شود."
)


url = st.text_input(
    "آدرس URL",
    placeholder="https://example.com",
)


inspect_button = st.button(
    "🔍 بررسی صفحه",
    type="primary",
    use_container_width=True,
)


# =========================================
# Run inspection
# =========================================

if inspect_button:

    normalized_url = normalize_url(
        url
    )

    if not normalized_url:

        st.error(
            "لطفاً یک URL وارد کنید."
        )

    else:

        progress = st.progress(
            0
        )

        status = st.empty()

        status.info(
            "در حال راه‌اندازی Chromium..."
        )

        progress.progress(
            10
        )

        status.info(
            "در حال باز کردن صفحه..."
        )

        progress.progress(
            20
        )

        result = fetch_page_data(
            normalized_url
        )

        progress.progress(
            100
        )

        if not result["success"]:

            status.empty()

            st.error(
                result["error"]
            )

        else:

            status.success(
                "صفحه با موفقیت بررسی شد."
            )

            # =================================
            # Basic information
            # =================================

            st.subheader(
                "📌 اطلاعات صفحه"
            )

            col1, col2 = st.columns(
                2
            )

            with col1:

                st.write(
                    "**Title:**",
                    result["title"]
                )

                st.write(
                    "**Final URL:**",
                    result["current_url"]
                )

            with col2:

                document = (
                    result[
                        "html_analysis"
                    ]["document"]
                )

                st.metric(
                    "HTML Length",
                    f"{document['html_length']:,}"
                )

                st.metric(
                    "Links",
                    document["links_count"]
                )

            # =================================
            # Screenshot
            # =================================

            st.subheader(
                "📸 Screenshot"
            )

            st.image(
                result[
                    "screenshot_png"
                ],
                caption=result["title"],
                use_container_width=True,
            )

            st.download_button(
                label="⬇️ دانلود Screenshot",
                data=result[
                    "screenshot_png"
                ],
                file_name="latest_screenshot.png",
                mime="image/png",
            )

            # =================================
            # Page state
            # =================================

            with st.expander(
                "⚙️ Page State"
            ):

                st.json(
                    result[
                        "page_state"
                    ]
                )

            # =================================
            # Stability
            # =================================

            with st.expander(
                "⏳ Stability Information"
            ):

                st.write(
                    "Initial Stability"
                )

                st.json(
                    result[
                        "initial_stability"
                    ]
                )

                st.write(
                    "Final Stability"
                )

                st.json(
                    result[
                        "final_stability"
                    ]
                )

            # =================================
            # Document
            # =================================

            analysis = result[
                "html_analysis"
            ]

            with st.expander(
                "📊 Document Analysis",
                expanded=True,
            ):

                st.json(
                    analysis[
                        "document"
                    ]
                )

            # =================================
            # Headings
            # =================================

            with st.expander(
                "🔤 Headings"
            ):

                st.json(
                    analysis[
                        "headings"
                    ]
                )

            # =================================
            # Semantic
            # =================================

            with st.expander(
                "🏗 Semantic Sections"
            ):

                st.json(
                    analysis[
                        "semantic_sections"
                    ]
                )

            # =================================
            # Forms
            # =================================

            with st.expander(
                "📝 Forms"
            ):

                if analysis["forms"]:

                    st.json(
                        analysis["forms"]
                    )

                else:

                    st.info(
                        "No forms found."
                    )

            # =================================
            # Tables
            # =================================

            with st.expander(
                "📋 Tables"
            ):

                if analysis["tables"]:

                    st.json(
                        analysis["tables"]
                    )

                else:

                    st.info(
                        "No tables found."
                    )

            # =================================
            # Links
            # =================================

            with st.expander(
                "🔗 Top Links"
            ):

                st.json(
                    analysis[
                        "top_links"
                    ]
                )

            # =================================
            # Images
            # =================================

            with st.expander(
                "🖼 Top Images"
            ):

                st.json(
                    analysis[
                        "top_images"
                    ]
                )

            # =================================
            # JSON-LD
            # =================================

            with st.expander(
                "🧩 JSON-LD"
            ):

                if analysis[
                    "json_ld_blocks"
                ]:

                    st.code(
                        "\n\n".join(
                            analysis[
                                "json_ld_blocks"
                            ]
                        ),
                        language="json",
                    )

                else:

                    st.info(
                        "No JSON-LD blocks found."
                    )

            # =================================
            # DOM
            # =================================

            with st.expander(
                "🌳 DOM Outline"
            ):

                st.code(
                    "\n".join(
                        analysis[
                            "dom_outline"
                        ]
                    ),
                    language="text",
                )

            # =================================
            # Text
            # =================================

            with st.expander(
                "📄 Text Preview"
            ):

                st.text_area(
                    "Rendered Text",
                    analysis[
                        "text_preview"
                    ],
                    height=400,
                )

            # =================================
            # HEAD
            # =================================

            with st.expander(
                "🧠 HEAD HTML"
            ):

                st.code(
                    analysis[
                        "head_html"
                    ],
                    language="html",
                )

            # =================================
            # MAIN
            # =================================

            with st.expander(
                "🎯 MAIN HTML"
            ):

                if analysis[
                    "main_html"
                ]:

                    st.code(
                        analysis[
                            "main_html"
                        ],
                        language="html",
                    )

                else:

                    st.info(
                        "No <main> element found."
                    )

            # =================================
            # BODY
            # =================================

            with st.expander(
                "📦 BODY HTML"
            ):

                st.code(
                    analysis[
                        "body_html"
                    ],
                    language="html",
                )

            # =================================
            # Full HTML
            # =================================

            with st.expander(
                "🌐 Full Rendered HTML"
            ):

                st.code(
                    result["html"],
                    language="html",
                )

            # =================================
            # Download HTML
            # =================================

            st.download_button(
                label="⬇️ دانلود Rendered HTML",
                data=result["html"],
                file_name="rendered_page.html",
                mime="text/html",
            )
