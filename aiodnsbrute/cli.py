import random
import string
import asyncio
import functools
import os
import uvloop
import aiodns
import click
import socket
import sys
from tqdm import tqdm

class aioDNSBrute(object):
    """Description goes here eventually..."""

    def __init__(self, verbosity=0, max_tasks=512):
        self.verbosity = verbosity
        self.tasks = []
        self.errors = []
        self.fqdn = []
        self.ignore_hosts = []
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        self.loop = asyncio.get_event_loop()
        self.resolver = aiodns.DNSResolver(loop=self.loop, rotate=True)
        self.sem = asyncio.BoundedSemaphore(max_tasks)
        self.max_tasks = max_tasks

    def logger(self, msg, msg_type='info', level=1):
        """A quick and dirty msfconsole style stdout logger."""
        if level <= self.verbosity:
            style = {'info': ('[*]', 'blue'), 'pos': ('[+]', 'green'), 'err': ('[-]', 'red'),
                     'warn': ('[!]', 'yellow'), 'dbg': ('[D]', 'cyan')}
            if msg_type is not 0:
                decorator = click.style(f'{style[msg_type][0]}', fg=style[msg_type][1], bold=True)
            else:
                decorator = ''
            m = f'{decorator} {msg}'
            tqdm.write(m)

    async def _dns_lookup(self, name, _type='A'):
        """Performs a DNS request using aiodns, returns an asyncio future."""
        response = await self.resolver.query(name, _type)
        return response

    def _dns_result_callback(self, name, future):
        """Handles the result passed by the _dns_lookup function."""
        # Record processed we can now release the lock
        self.sem.release()
        # Handle known exceptions, barf on other ones
        if future.exception() is not None:
            try:
                err_num = future.exception().args[0]
                err_text = future.exception().args[1]
            except IndexError:
                self.logger(f'Couldn\'t parse exception: {future.exception()}', 'err')
            if (err_num == 4): # This is domain name not found, ignore it.
                pass
            elif (err_num == 12): # Timeout from DNS server
                self.logger(f'Timeout for {name}', 'warn', 2)
            elif (err_num == 1): # Server answered with no data
                pass
            else:
                self.logger(f'{name} generated an unexpected exception: {future.exception()}', 'err')
            #self.errors.append({'hostname': name, 'error': err_text})
        # Output result
        else:
            ip = ', '.join([ip.host for ip in future.result()])
            if ip not in self.ignore_hosts:
                self.logger(f'{name:<30}\t{ip}', 'pos')
                self.fqdn.append({'domain': name, 'ip': [ip]})
            self.logger(future.result(), 'dbg', 3)
        self.tasks.remove(future)
        if self.verbosity >= 1:
            self.pbar.update()

    async def _process_dns_wordlist(self, wordlist, domain):
        """Takes a list of words and adds them to the task list as space is available"""
        for word in wordlist:
            # Wait on the semaphore before adding more tasks
            await self.sem.acquire()
            host = f'{word.strip()}.{domain}'
            task = asyncio.ensure_future(self._dns_lookup(host))
            task.add_done_callback(functools.partial(self._dns_result_callback, host))
            self.tasks.append(task)
        await asyncio.gather(*self.tasks, return_exceptions=True)

    def run(self, wordlist, domain, resolvers=None, wildcard=True, verify=True):
        self.logger(f'Brute forcing {domain} with a maximum of {self.max_tasks} concurrent tasks...')
        if verify:
            self.logger(f'Using local resolver to verify {domain} exists.')
            try:
                socket.gethostbyname(domain)
            except socket.gaierror as err:
                self.logger(f'Couldn\'t resolve {domain}, use the --no-verify switch to ignore this error.', 'err')
                raise SystemExit(self.logger(f'Error from host lookup: {err}', 'err'))
        else:
            self.logger('Skipping domain verification. YOLO!', 'warn')
        if resolvers:
            self.resolver.nameservers = resolvers
        self.logger(f'Using recursive DNS with the following servers: {self.resolver.nameservers}')
        if wildcard:
            # 63 chars is the max allowed segment length, there is practically no chance that it will be a legit record
            random_sld = lambda: f'{"".join(random.choice(string.ascii_lowercase + string.digits) for i in range(63))}'
            try:
                wc_check = self.loop.run_until_complete(self._dns_lookup(f'{random_sld()}.{domain}'))
            except aiodns.error.DNSError as err:
                # we expect that the record will not exist and error 4 will be thrown
                self.logger(f'No wildcard response was detected for this domain.')
                wc_check = None
            finally:
                if wc_check is not None:
                    self.ignore_hosts = [host.host for host in wc_check]
                    self.logger(f'Wildcard response detected, ignoring answers containing {self.ignore_hosts}', 'warn')
        else:
            self.logger('Wildcard detection is disabled', 'warn')

        with open(wordlist, encoding='utf-8', errors='ignore') as words:
            w = words.read().splitlines()
        self.logger(f'Wordlist loaded, proceeding with {len(w)} DNS requests')
        try:
            if self.verbosity >= 1:
                self.pbar = tqdm(total=len(w), unit="records", maxinterval=0.1, mininterval=0)
            self.loop.run_until_complete(self._process_dns_wordlist(w, domain))
        except KeyboardInterrupt:
            self.logger("Caught keyboard interrupt, cleaning up...")
            asyncio.gather(*asyncio.Task.all_tasks()).cancel()
            self.loop.stop()
        finally:
            self.loop.close()
            if self.verbosity >= 1:
                self.pbar.close()
            self.logger(f'Completed, {len(self.fqdn)} subdomains found')
        return self.fqdn

## NOTE: Remember to remove recursive stuff

@click.command()
@click.option('--wordlist', '-w', help='Wordlist to use for brute force.',
              default=f'{os.path.dirname(os.path.realpath(__file__))}/wordlists/bitquark_20160227_subdomains_popular_1000')
@click.option('--max-tasks', '-t', default=512,
              help='Maximum number of tasks to run asynchronosly.')
@click.option('--resolver-file', '-r', type=click.File('r'), default=None, help="A text file containing a list of DNS resolvers to use, one per line, comments start with #. Default: use system resolvers")
@click.option('--verbosity', '-v', count=True, default=1, help="Increase output verbosity")
@click.option('--output', '-o', type=click.Choice(['csv', 'json', 'off']), default='off', help="Output results to DOMAIN.csv/json (extension automatically appended when not using -f).")
@click.option('--outfile', '-f', type=click.File('w'), help="Output filename. Use '-f -' to send file output to stdout overriding normal output.")
@click.option('--wildcard/--no-wildcard', default=True, help="Wildcard detection, enabled by default")
@click.option('--verify/--no-verify', default=True, help="Verify domain name is sane before beginning, enabled by default")
@click.version_option('0.2.1')
@click.argument('domain', required=True)
def main(**kwargs):
    """aiodnsbrute is a command line tool for brute forcing domain names utilizing Python's asyncio module.

    credit: blark (@markbaseggio)
    """
    output = kwargs.get('output')
    verbosity = kwargs.get('verbosity')
    resolvers = kwargs.get('resolver_file')
    if output is not 'off':
        outfile = kwargs.get('outfile')
        # turn off output if we want JSON/CSV to stdout, hacky
        if outfile.__class__.__name__ == 'TextIOWrapper':
            verbosity = 0
        if outfile is None:
            # wasn't specified on command line
            outfile = open(f'{kwargs["domain"]}.{output}', 'w')
    if resolvers:
        lines = resolvers.read().splitlines()
        resolvers = [x.strip() for x in lines if (x and not x.startswith('#'))]

    bf = aioDNSBrute(verbosity=verbosity, max_tasks=kwargs.get('max_tasks'))
    results = bf.run(wordlist=kwargs.get('wordlist'), domain=kwargs.get('domain'), resolvers=resolvers, wildcard=kwargs.get('wildcard'), verify=kwargs.get('verify'))

    if output in ('json'):
        import json
        json.dump(results, outfile)
    if output in ('csv'):
        import csv
        writer = csv.writer(outfile)
        writer.writerow(['Hostname', 'IPs'])
        [writer.writerow([r.get('domain'), r.get('ip')[0]]) for r in results]

if __name__ == '__main__':
    main()
