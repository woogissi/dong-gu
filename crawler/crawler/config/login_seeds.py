# crawler/config/login_seeds.py

LOGIN_SEEDS = [
    {
        "name": "dap_login",
        "url": "https://dap.deu.ac.kr/sso/login.aspx",
        "source_type": "dap",
        "page_kind": "login_page",
        "login_type": "dap",
        "children": [
            {
                "name": "dap_dept_timetable",
                "url": "https://dap.deu.ac.kr/Student/UCB/UCB0613R.aspx?mcd=111974&pid=Ucb0613r",
                "source_type": "dap",
                "page_kind": "dynamic_report_page",
                "report_type": "select_iframe_report",
                "selects": {
                    "semester": "#CP1_ddl_smt",
                    "department": "#CP1_ddl_dept",
                },
                "submit": "#CP1_BtnOk",
                "iframe": "#ifrm_rpt",
            },
            {
                "name": "dap_StdNotice_board",
                "url": "https://dap.deu.ac.kr/StdNotice.aspx",
                "source_type": "dap",
                "page_kind": "board_list",
                "pages": 50,
                "page_size": 15,
            },
        ],
    }
]