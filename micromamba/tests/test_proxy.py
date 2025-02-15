import asyncio
import os
import shutil
import time
import urllib.parse
from pathlib import Path
from subprocess import TimeoutExpired

from .helpers import *


class TestProxy:

    current_root_prefix = os.environ["MAMBA_ROOT_PREFIX"]
    current_prefix = os.environ["CONDA_PREFIX"]

    env_name = random_string()
    root_prefix = os.path.expanduser(os.path.join("~", "tmproot" + random_string()))
    prefix = os.path.join(root_prefix, "envs", env_name)

    mitm_exe = shutil.which("mitmdump")
    mitm_confdir = os.path.join(root_prefix, "mitmproxy")
    mitm_dump_path = os.path.join(root_prefix, "dump.json")

    proxy_process = None

    @classmethod
    def setup_class(cls):
        os.environ["MAMBA_ROOT_PREFIX"] = TestProxy.root_prefix
        os.environ["CONDA_PREFIX"] = TestProxy.prefix

    def setup_method(self):
        create("-n", TestProxy.env_name, "--offline", no_dry_run=True)

    @classmethod
    def teardown_class(cls):
        os.environ["MAMBA_ROOT_PREFIX"] = TestProxy.current_root_prefix
        os.environ["CONDA_PREFIX"] = TestProxy.current_prefix

    def teardown_method(self):
        shutil.rmtree(TestProxy.root_prefix)

    def start_proxy(self, port, options=[]):
        assert self.proxy_process is None
        script = Path(__file__).parent / "dump_proxy_connections.py"
        self.proxy_process = subprocess.Popen(
            [
                TestProxy.mitm_exe,
                "--listen-port",
                str(port),
                "--scripts",
                script,
                "--set",
                f"outfile={TestProxy.mitm_dump_path}",
                "--set",
                f"confdir={TestProxy.mitm_confdir}",
                *options,
            ]
        )

        # Wait until mitmproxy has generated its certificate or some tests might fail
        while not (Path(TestProxy.mitm_confdir) / "mitmproxy-ca-cert.pem").exists():
            time.sleep(1)

    def stop_proxy(self):
        self.proxy_process.terminate()
        try:
            self.proxy_process.wait(3)
        except TimeoutExpired:
            self.proxy_process.kill()
        self.proxy_process = None

    @pytest.mark.parametrize(
        "auth",
        [
            None,
            "foo:bar",
            "user%40example.com:pass",
        ],
    )
    @pytest.mark.parametrize("ssl_verify", (True, False))
    def test_install(self, unused_tcp_port, auth, ssl_verify):
        """
        This test makes sure micromamba follows the proxy settings in .condarc

        It starts mitmproxy with the `dump_proxy_connections.py` script, which dumps all requested urls in a text file.
        After that micromamba is used to install a package, while pointing it to that mitmproxy instance. Once
        micromamba finished the proxy server is stopped and the urls micromamba requested are compared to the urls
        mitmproxy intercepted, making sure that all the requests went through the proxy.
        """

        if auth is not None:
            proxy_options = ["--proxyauth", urllib.parse.unquote(auth)]
            proxy_url = "http://{}@localhost:{}".format(auth, unused_tcp_port)
        else:
            proxy_options = []
            proxy_url = "http://localhost:{}".format(unused_tcp_port)

        self.start_proxy(unused_tcp_port, proxy_options)

        cmd = ["xtensor"]
        f_name = random_string() + ".yaml"
        rc_file = os.path.join(TestProxy.prefix, f_name)

        if ssl_verify:
            verify_string = os.path.abspath(
                os.path.join(TestProxy.mitm_confdir, "mitmproxy-ca-cert.pem")
            )
        else:
            verify_string = "false"

        file_content = [
            "proxy_servers:",
            "    http: {}".format(proxy_url),
            "    https: {}".format(proxy_url),
            "ssl_verify: {}".format(verify_string),
        ]
        with open(rc_file, "w") as f:
            f.write("\n".join(file_content))

        cmd += ["--rc-file", rc_file]

        if os.name == "nt":
            # The certificates generated by mitmproxy don't support revocation.
            # The schannel backend curl uses on Windows fails revocation check if revocation isn't supported. Other
            # backends succeed revocation check in that case.
            cmd += ["--ssl-no-revoke"]

        res = install(*cmd, "--json", no_rc=False)

        self.stop_proxy()

        with open(TestProxy.mitm_dump_path, "r") as f:
            proxied_requests = f.read().splitlines()

        for fetch in res["actions"]["FETCH"]:
            assert fetch["url"] in proxied_requests
