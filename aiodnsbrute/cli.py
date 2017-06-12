import asyncio
import functools
import uvloop
import aiodns
import click
from tqdm import tqdm

class aioDNSBrute(object):
    """Description goes here eventually..."""

    def __init__(self, verbosity=0, max_tasks=512):
        self.verbosity = verbosity
        self.tasks = []
        self.errors = []
        self.fqdn = []
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        self.loop = asyncio.get_event_loop()
        self.resolver = aiodns.DNSResolver(loop=self.loop)
        self.sem = asyncio.Semaphore(max_tasks)
        self.pbar = None

    def logger(self, msg, msg_type='info', level=1):
        """A quick and dirty msfconsole style stdout logger."""
        if level <= self.verbosity:
            style = {'info': ('[*]', 'blue'), 'pos': ('[+]', 'green'), 'err': ('[-]', 'red'),
                     'warn': ('[!]', 'yellow'), 'dbg': ('[D]', 'cyan')}
            if msg_type is not 0:
                decorator = click.style('{}'.format(style[msg_type][0]), fg=style[msg_type][1], bold=True)
            else:
                decorator = ''
            m = "{} {}".format(decorator, msg)
            tqdm.write(m)

    async def lookup(self, name):
        """Performs a DNS request using aiodns, returns an asyncio future."""
        with (await self.sem):
            response = await self.resolver.query(name, 'A')
            return response

    def got_result(self, name, future):
        """Handles the result passed by the lookup function."""
        # Deal with exceptions
        if future.exception() is not None:
            err_num = future.exception().args[0]
            err_text = future.exception().args[1]
            if (err_num == 4): # This is domain name not found, ignore it.
                pass
            elif (err_num == 12): # Timeout from DNS server
                self.logger("Timeout for {}".format(name), 'warn', 2)
            elif (err_num == 1): # Server answered with no data
                pass
            else:
                self.logger('{} generated an unexpected exception: {}'.format(name, future.exception()), 'err')
            self.errors.append({'hostname': name, 'error': err_text})
        else:
            self.fqdn.append(('name', future.result()))
            self.logger("{}\t{}".format(name, future.result()), 'pos')
        if self.verbosity >= 1:
            self.pbar.update()

    def run(self, wordlist, domain):
        # Read the wordlist file
        self.logger("Opening wordlist: {}".format(wordlist), 'dbg', 2)
        with open(wordlist) as f:
            subdomains = f.read().splitlines()
        # Add each subdomain in the wordlist to the task list
        self.logger("Adding {} subdomains to task list.".format(len(subdomains)), 'dbg', 2)
        for n in subdomains:
            host = '{}.{}'.format(n, domain)
            task = asyncio.ensure_future(self.lookup(host))
            task.add_done_callback(functools.partial(self.got_result, host))
            self.tasks.append(task)
        if self.verbosity >= 1:
            self.pbar = tqdm(total=len(subdomains), unit="rec", maxinterval=0.1, mininterval=0)
        self.logger("Starting {} DNS lookups for {}...".format(len(subdomains), domain))
        try:
            self.loop.run_until_complete(asyncio.wait(self.tasks))
        except KeyboardInterrupt:
            self.logger("Caught keyboard interrupt, cleaning up...")
            asyncio.gather(*asyncio.Task.all_tasks()).cancel()
            self.loop.stop()
        finally:
            self.loop.close()
            self.pbar.close()

@click.command()
@click.option('--wordlist', '-w', help='Wordlist to use for brute force.',
              default='./wordlists/bitquark_20160227_subdomains_popular_1000')
@click.option('--max-tasks', '-t', default=512,
              help='Maximum number of tasks to run asynchronosly.')
@click.option('--verbosity', '-v', count=True, default=1, help="Turn on/increase output.")
@click.argument('domain', required=True)
def main(wordlist, domain, max_tasks, verbosity):
    """Brute force DNS domain names asynchronously"""
    bf = aioDNSBrute(verbosity=verbosity, max_tasks=max_tasks)
    bf.run(wordlist=wordlist, domain=domain)

if __name__ == '__main__':
    main()
