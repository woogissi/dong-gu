# crawler/config/login_seeds.py

LOGIN_SEEDS = [{'name': 'dap_login',
  'url': 'https://dap.deu.ac.kr/sso/login.aspx',
  'source_type': 'dap',
  'page_kind': 'login_page',
  'login_type': 'dap',
  'children': [
                {"name": "dap_ucb0510q",
                "source_type": "dap",
                "page_kind": "dynamic_report_page",
                "report_type": "select_postback_result",
                "url": "https://dap.deu.ac.kr/Student/UCB/UCB0510Q.aspx?mcd=111968&pid=Ucb0510q",
                "dependent_selects": [
                        ["semester", "department"]
                    ],
                "max_combinations": 10,
                "controls": {
                    "selects": {
                        "semester": {
                            "selector": "#CP1_ddl_smt",
                            "select_by": "value"
                        },
                        "department": {
                            "selector": "#CP1_ddl_dept_cd",
                            "select_by": "value",
                            "required": False
                        }
                    },
                    "submit": {
                        "selector": "#CP1_BtnOk",
                        "click": True
                    }
                },
                "result": {
                    "selector": "#CP1_dt_result",
                    "no_data_texts": ["해당 자료가 없습니다"],
                    "exclude_selectors": [
                        "#CP1_tbl_list",
                        "#CP1_commandbar",
                        "select",
                        "option",
                        "input",
                        "button",
                        "script",
                        "style"
                    ]
                }
            },
                                                 
                {"name": "dap_ucb0309r_room",
                "url": "https://dap.deu.ac.kr/Student/UCB/UCB0309R.aspx?mcd=111970&pid=Ucb0309r",
                "source_type": "dap",
                "page_kind": "dynamic_report_page",
                "report_type": "select_iframe_report",
                "dependent_selects": [
                        ["semester", "type", "building", "room"]
                    ],
                "max_combinations": 10,
                "controls": {
                    "inputs": {
                        "year": {
                            "selector": "#CP1_txt_year",
                            "value": "2026"
                        }
                    },
                    "selects": {
                        "semester": {
                            "selector": "#CP1_ddl_smt",
                            "select_by": "value",
                            "include_values": ["10", "20"]
                        },
                        "type": {
                            "selector": "#CP1_ddl_gbn",
                            "select_by": "value",
                            "include_values": ["02"]
                        },
                        "building": {
                            "selector": "#CP1_ddl_bld_nm",
                            "select_by": "value"
                        },
                        "room": {
                            "selector": "#CP1_ddl_room_cd",
                            "select_by": "value"
                        }
                    },
                    "submit": {
                        "selector": "#CP1_BtnOk",
                        "click": True
                    },
                    "iframe": {
                        "selector": "#ifrm_rpt"
                    }
                },

                "result": {
                    "type": "pdf_download"
                }
            },
                {"name": "dap_ucb0309r_professor",
                "url": "https://dap.deu.ac.kr/Student/UCB/UCB0309R.aspx?mcd=111970&pid=Ucb0309r",
                "source_type": "dap",
                "page_kind": "dynamic_report_page",
                "report_type": "popup_lookup_iframe_report",
                "max_combinations": 10,
                "controls": {
                    "inputs": {
                        "year": {
                            "selector": "#CP1_txt_year",
                            "value": "2026"
                        },
                    },
                    "selects": {
                        "semester": {
                            "selector": "#CP1_ddl_smt",
                            "select_by": "value",
                            "include_values": ["10", "20"]
                        },
                        "type": {
                            "selector": "#CP1_ddl_gbn",
                            "select_by": "value",
                            "include_values": ["01"]
                        },
                    },
                    "lookup": {
                        "open_button": "#CP1_btn_emp_search",
                        "popup_url_contains": "AdmStuEmpSearch.aspx",
                        "search_button": "#CP1_btnSearch",
                        "result_table": "#CP1_dt_result",
                        "value_column_index": 0,
                        "text_column_index": 1,
                        "pager": {
                            "page_count_selector": "#CP1_COM_Page_Controllor_hdnPageCnt",
                            "page_link_prefix": "#CP1_COM_Page_Controllor_lbtnPage"
                        },
                    },
                    "target_input": {
                        "selector": "#CP1_txt_emp_id"
                    },
                    "submit": {
                        "selector": "#CP1_BtnOk",
                        "click": True
                    },
                    "iframe": {
                        "selector": "#ifrm_rpt"
                    },
                },

                "result": {
                    "type": "pdf_download",
                    "no_data_texts": ["해당 자료가 없습니다"]
                }
            },
               
               
               
               
               ]}]
