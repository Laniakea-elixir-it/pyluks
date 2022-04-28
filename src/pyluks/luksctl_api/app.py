from pyluks.luksctl_api.luksctl_api_master import app as master_app

if __name__ == '__main__':
    master_app.run(host='0.0.0.0:5000', debug=True)