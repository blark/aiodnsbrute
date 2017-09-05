# Async DNS Brute

A Python 3.5+ script that uses asyncio to brute force domain names asynchronously.

![aiodnsbrute screenshot](screenshot.png)

## Speed

*It's fast.* Benchmarks on small VPS hosts put around 100k DNS resoultions at 1.5-2mins. An amazon M3 box was used to make 1 mil requests in just over 3 minutes. Your mileage may vary. It's probably best to avoid using Google's resolvers if you're purely interested in speed.

## Todo

Right now the script just uses the system's DNS resolvers. I'll be adding a feature to read in a list of resolvers from a text file.

# Installation

If you don't use `pipsi`, you're missing out.
Here are [installation instructions](https://github.com/mitsuhiko/pipsi#readme).

## Debian/Kali/Ubuntu

The following should get you up and running.

    $ sudo apt-get install python3-pip
    $ sudo pip3 install virtualenv
    $ curl https://raw.githubusercontent.com/mitsuhiko/pipsi/master/get-pipsi.py | python3

...add pipsi path to your .bashrc, source bashrc file

    $ git clone https://github.com/blark/aiodnsbrute.git
    $ cd aiodnsbrute
    $ pipsi install .

## Usage

Get help with:

    $ aiodnsbrute --help

    Usage: aiodnsbrute [OPTIONS] DOMAIN

      Brute force DNS domain names asynchronously

    Options:
      -w, --wordlist TEXT      Wordlist to use for brute force.
      -t, --max-tasks INTEGER  Maximum number of tasks to run asynchronosly.
      -v, --verbosity          Turn on/increase output.
      --help                   Show this message and exit.

Run a brute force with some custom options:

    $ aiodnsbrute -w wordlist.txt -vv -t 1024 domain.com

*note* you might want to do a `ulimit -n` to see how many open files are allowed. You can also increase that number using the same command, i.e. `ulimit -n <2048>`
