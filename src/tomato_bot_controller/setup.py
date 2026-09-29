from setuptools import find_packages, setup

package_name = 'tomato_bot_controller'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', [
            'config/tomato_bot_rviz.rviz',
            'config/safe_nav_defaults.yaml',
        ]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ylubt2204',
    maintainer_email='1154694565@qq.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'keyboard_control = tomato_bot_controller.keyboard_control:main',
            'navdp_pointgoal_client = tomato_bot_controller.navdp_pointgoal_client:main',
            'navdp_imggoal_client = tomato_bot_controller.navdp_imggoal_client:main',
            'navdp_nogoal_client = tomato_bot_controller.navdp_nogoal_client:main',
            'navdp_mixgoal_client = tomato_bot_controller.navdp_mixgoal_client:main',
        ],
    },
)
