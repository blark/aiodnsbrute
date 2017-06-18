import asyncio
import functools
import os
import uvloop
import aiodns
import click
import socket
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
        self.resolver = aiodns.DNSResolver(loop=self.loop, rotate=True)
        self.sem = asyncio.BoundedSemaphore(max_tasks)
        self.max_tasks = max_tasks

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
                self.logger("Couldn't parse exception: {}".format(future.exception()), 'err')
            if (err_num == 4): # This is domain name not found, ignore it.
                pass
            elif (err_num == 12): # Timeout from DNS server
                self.logger("Timeout for {}".format(name), 'warn', 2)
            elif (err_num == 1): # Server answered with no data
                pass
            else:
                self.logger('{} generated an unexpected exception: {}'.format(name, future.exception()), 'err')
            #self.errors.append({'hostname': name, 'error': err_text})
        # Output result
        else:
            ip = ', '.join([ip.host for ip in future.result()])
            self.fqdn.append((name, ip))
            self.logger("{:<30}\t{}".format(name, ip), 'pos')
            self.logger(future.result(), 'dbg', 3)
        self.tasks.remove(future)
        if self.verbosity >= 1:
            self.pbar.update()

    async def _process_dns_wordlist(self, wordlist, domain):
        """Takes a list of words and adds them to the task list as space is available"""
        for word in wordlist:
            # Wait on the semaphore before adding more tasks
            await self.sem.acquire()
            host = '{}.{}'.format(word.strip(), domain)
            task = asyncio.ensure_future(self._dns_lookup(host))
            task.add_done_callback(functools.partial(self._dns_result_callback, host))
            self.tasks.append(task)
        await asyncio.gather(*self.tasks, return_exceptions=True)

    def run(self, wordlist, domain, recursive=True):
        try:
            self.logger("Brute forcing {} with a maximum of {} concurrent tasks...".format(domain, self.max_tasks))
            with open(wordlist) as words:
                w = words.read().splitlines()
            self.logger("Wordlist loaded, brute forcing {} DNS records".format(len(w)))
            if self.verbosity >= 1:
                self.pbar = tqdm(total=len(w), unit="records", maxinterval=0.1, mininterval=0)
            if recursive:
                self.logger("Using recursive DNS with the following servers: {}".format(self.resolver.nameservers))
            else:
                domain_ns = self.loop.run_until_complete(self._dns_lookup(domain, 'NS'))
                self.logger("Setting nameservers to {} domain NS servers: {}".format(domain, [host.host for host in domain_ns]))
                self.resolver.nameservers = [socket.gethostbyname(host.host) for host in domain_ns]
            self.loop.run_until_complete(self._process_dns_wordlist(w, domain))
        except KeyboardInterrupt:
            self.logger("Caught keyboard interrupt, cleaning up...")
            asyncio.gather(*asyncio.Task.all_tasks()).cancel()
            self.loop.stop()
        finally:
            self.loop.close()
            if self.verbosity >= 1:
                self.pbar.close()
            self.logger("completed, {} subdomains found.".format(len(self.fqdn)))
        return self.fqdn


@click.command()
@click.option('--wordlist', '-w', help='Wordlist to use for brute force.',
              default='{}/wordlists/bitquark_20160227_subdomains_popular_1000'.format(os.path.dirname(os.path.realpath(__file__))))
@click.option('--max-tasks', '-t', default=512,
              help='Maximum number of tasks to run asynchronosly.')
@click.option('--verbosity', '-v', count=True, default=1, help="Turn on/increase output.")
@click.option('--recursive/--direct', '-r/-d', default=True, help="Recursive or direct DNS requests.")
@click.option('--output', '-o', default=None, help="Filename to save results to (saves as CSV).")
@click.argument('domain', required=True)
def main(wordlist, domain, max_tasks, verbosity, recursive, output):
    """Brute force DNS domain names asynchronously"""
    import csv
    bf = aioDNSBrute(verbosity=verbosity, max_tasks=max_tasks)
    results = bf.run(wordlist=wordlist, domain=domain, recursive=recursive)
    if output is not None:
        with open(output, "w") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(['Hostname', 'IPs'])
            writer.writerows(results)

if __name__ == '__main__':
    main()
